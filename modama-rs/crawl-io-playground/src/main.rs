//! Playground (python/crawler benchmark): the crawl's I/O in Rust. Lists, lstats and
//! classifies every regular file under ROOT with xdg-mime against a given shared-mime-info
//! directory, reading the first bytes only where the globs do not decide, as the
//! crawler's mime.py does. Not production code.
//!
//!   crawl-io-playground ROOT --mimedb DIR [--threads N] [--read plain|fadvise|odirect]
//!                       [--uring QD] [--bytes K] [--out FILE]
//!
//! --uring QD: header reads go to one io_uring thread with QD files in flight, each a
//! linked chain openat -> fadvise -> read -> close on a fixed-file slot; listing and
//! lstat stay in the N threads (io_uring has no getdents).

use std::alloc::{Layout, alloc_zeroed, dealloc};
use std::collections::VecDeque;
use std::ffi::CString;
use std::io::Write;
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::{FileExt, OpenOptionsExt};
use std::path::{Path, PathBuf};
use std::sync::mpsc;
use std::sync::{Arc, Condvar, Mutex};
use std::time::Instant;

use xdg_mime::SharedMimeInfo;

#[derive(Clone, Copy, PartialEq)]
enum ReadMode {
    Plain,
    Fadvise,
    Odirect,
}

struct Opts {
    root: PathBuf,
    mimedb: PathBuf,
    threads: usize,
    read: ReadMode,
    uring: usize,
    bytes: usize,
    out: Option<PathBuf>,
    defer_stat: bool,
}

fn parse_args() -> Opts {
    let mut args = std::env::args().skip(1);
    let mut o = Opts {
        root: PathBuf::new(),
        mimedb: PathBuf::new(),
        threads: 1,
        read: ReadMode::Plain,
        uring: 0,
        bytes: 0,
        out: None,
        defer_stat: false,
    };
    while let Some(a) = args.next() {
        let mut val = || args.next().unwrap_or_else(|| panic!("{a} needs a value"));
        match a.as_str() {
            "--mimedb" => o.mimedb = val().into(),
            "--threads" => o.threads = val().parse().unwrap(),
            "--uring" => o.uring = val().parse().unwrap(),
            "--bytes" => o.bytes = val().parse().unwrap(),
            "--out" => o.out = Some(val().into()),
            "--defer-stat" => o.defer_stat = true,
            "--read" => {
                o.read = match val().as_str() {
                    "plain" => ReadMode::Plain,
                    "fadvise" => ReadMode::Fadvise,
                    "odirect" => ReadMode::Odirect,
                    m => panic!("unknown read mode {m}"),
                }
            }
            _ => o.root = a.into(),
        }
    }
    o
}

/// A page-aligned buffer, so that O_DIRECT reads work.
struct Buf {
    ptr: *mut u8,
    layout: Layout,
}
unsafe impl Send for Buf {}
impl Buf {
    fn new(len: usize) -> Buf {
        let layout = Layout::from_size_align(len.div_ceil(4096).max(1) * 4096, 4096).unwrap();
        Buf { ptr: unsafe { alloc_zeroed(layout) }, layout }
    }
    fn slice(&mut self) -> &mut [u8] {
        unsafe { std::slice::from_raw_parts_mut(self.ptr, self.layout.size()) }
    }
}
impl Drop for Buf {
    fn drop(&mut self) {
        unsafe { dealloc(self.ptr, self.layout) }
    }
}

enum Task {
    Dir(PathBuf),
    File(PathBuf, u64),
}

/// FIFO work queue with a count of unfinished tasks; workers stop when it reaches 0.
struct Queue {
    state: Mutex<(VecDeque<Task>, usize)>,
    cv: Condvar,
}
impl Queue {
    fn push(&self, t: Task) {
        let mut s = self.state.lock().unwrap();
        s.0.push_back(t);
        s.1 += 1;
        self.cv.notify_one();
    }
    fn pop(&self) -> Option<Task> {
        let mut s = self.state.lock().unwrap();
        loop {
            if let Some(t) = s.0.pop_front() {
                return Some(t);
            }
            if s.1 == 0 {
                return None;
            }
            s = self.cv.wait(s).unwrap();
        }
    }
    fn done(&self) {
        let mut s = self.state.lock().unwrap();
        s.1 -= 1;
        if s.1 == 0 {
            self.cv.notify_all();
        }
    }
}

const OCTET: &str = "application/octet-stream";

/// The glob candidates (empty if no glob matched); one candidate decides without reading.
fn glob_candidates(db: &SharedMimeInfo, name: &str) -> Vec<String> {
    let c: Vec<String> = db
        .get_mime_types_from_file_name(name)
        .iter()
        .map(|m| m.essence_str().to_string())
        .collect();
    if c == [OCTET] { Vec::new() } else { c }
}

/// mime.py's decision after sniffing; a tie is reported as "TIE:" + candidates.
fn decide(db: &SharedMimeInfo, mut cands: Vec<String>, data: Option<&[u8]>) -> String {
    let Some(data) = data else {
        return if cands.is_empty() { OCTET.into() } else { format!("TIE:{}", cands.join(",")) };
    };
    let sniffed = if data.is_empty() {
        None
    } else {
        db.get_mime_type_for_data(data).map(|(m, _)| m.essence_str().to_string())
    };
    if cands.is_empty() {
        return sniffed.unwrap_or_else(|| {
            let text = !data.iter().take(32).any(|&b| b <= 8 || (0xe..0x20).contains(&b) || b == 0x7f);
            if text { "text/plain".into() } else { OCTET.into() }
        });
    }
    if let Some(s) = &sniffed {
        let sm: mime::Mime = s.parse().unwrap();
        let related: Vec<String> = cands
            .iter()
            .filter(|c| c.parse::<mime::Mime>().is_ok_and(|cm| db.mime_type_subclass(&cm, &sm)))
            .cloned()
            .collect();
        if related.contains(s) {
            return s.clone();
        }
        if related.len() == 1 {
            return related[0].clone();
        }
        if !related.is_empty() {
            cands = related;
        }
    }
    cands.sort();
    format!("TIE:{}", cands.join(","))
}

fn read_header(path: &Path, size: u64, k: usize, mode: ReadMode) -> std::io::Result<Vec<u8>> {
    let mut opts = std::fs::OpenOptions::new();
    opts.read(true);
    if mode == ReadMode::Odirect {
        opts.custom_flags(libc::O_DIRECT);
    }
    let f = opts.open(path)?;
    let size = if size == u64::MAX { f.metadata()?.len() } else { size };
    if mode == ReadMode::Fadvise {
        unsafe { libc::posix_fadvise(std::os::fd::AsRawFd::as_raw_fd(&f), 0, 0, libc::POSIX_FADV_RANDOM) };
    }
    let want = k.min(size as usize);
    let mut buf = Buf::new(want);
    let n = if mode == ReadMode::Odirect {
        f.read_at(buf.slice(), 0)?
    } else {
        f.read_at(&mut buf.slice()[..want], 0)?
    };
    Ok(buf.slice()[..n.min(want)].to_vec())
}

type Results = Arc<Mutex<Vec<(String, String)>>>;

struct Job {
    path: PathBuf,
    size: u64,
    cands: Vec<String>,
}

/// The io_uring thread: up to `depth` files in flight, each a linked chain on its own fixed slot.
fn ring_thread(
    rx: mpsc::Receiver<Job>,
    depth: usize,
    k: usize,
    mode: ReadMode,
    db: Arc<SharedMimeInfo>,
    root: PathBuf,
    results: Results,
    queue: Arc<Queue>,
) {
    use io_uring::{IoUring, opcode, squeue::Flags, types};
    let ops_per_file = if mode == ReadMode::Fadvise { 4 } else { 3 };
    let mut ring = IoUring::new((depth * ops_per_file).next_power_of_two() as u32).unwrap();
    ring.submitter().register_files_sparse(depth as u32).unwrap();
    struct Slot {
        job: Job,
        path: CString,
        buf: Buf,
        read_res: i32,
        left: usize,
    }
    let mut slots: Vec<Option<Slot>> = (0..depth).map(|_| None).collect();
    let mut inflight = 0;
    let mut open = true;
    while open || inflight > 0 {
        // Fill free slots; block for the first job only when nothing is in flight
        for i in 0..depth {
            if slots[i].is_some() || !open {
                continue;
            }
            let job = if inflight == 0 {
                match rx.recv() {
                    Ok(j) => j,
                    Err(_) => {
                        open = false;
                        continue;
                    }
                }
            } else {
                match rx.try_recv() {
                    Ok(j) => j,
                    Err(mpsc::TryRecvError::Empty) => break,
                    Err(mpsc::TryRecvError::Disconnected) => {
                        open = false;
                        continue;
                    }
                }
            };
            let want = k.min(job.size as usize);
            let mut s = Slot {
                path: CString::new(job.path.as_os_str().as_bytes()).unwrap(),
                buf: Buf::new(want),
                job,
                read_res: 0,
                left: ops_per_file,
            };
            let len = if mode == ReadMode::Odirect { s.buf.layout.size() } else { want } as u32;
            let flags = libc::O_RDONLY | if mode == ReadMode::Odirect { libc::O_DIRECT } else { 0 };
            let slot = types::DestinationSlot::try_from_slot_target(i as u32).unwrap();
            let fixed = types::Fixed(i as u32);
            let tag = (i as u64) << 8;
            let mut sqes = vec![
                opcode::OpenAt::new(types::Fd(libc::AT_FDCWD), s.path.as_ptr())
                    .flags(flags)
                    .file_index(Some(slot))
                    .build()
                    .flags(Flags::IO_LINK)
                    .user_data(tag),
            ];
            if mode == ReadMode::Fadvise {
                sqes.push(
                    opcode::Fadvise::new(fixed, 0, libc::POSIX_FADV_RANDOM)
                        .build()
                        .flags(Flags::IO_LINK)
                        .user_data(tag | 1),
                );
            }
            sqes.push(
                opcode::Read::new(fixed, s.buf.ptr, len)
                    .offset(0)
                    .build()
                    .flags(Flags::IO_HARDLINK)
                    .user_data(tag | 2),
            );
            sqes.push(opcode::Close::new(fixed).build().user_data(tag | 3));
            slots[i] = Some(s);
            inflight += 1;
            unsafe { ring.submission().push_multiple(&sqes).unwrap() };
        }
        if inflight == 0 {
            continue;
        }
        ring.submit_and_wait(1).unwrap();
        let cqes: Vec<_> = ring.completion().map(|c| (c.user_data(), c.result())).collect();
        for (ud, res) in cqes {
            let i = (ud >> 8) as usize;
            let s = slots[i].as_mut().unwrap();
            match ud & 0xff {
                0 if res < 0 => s.read_res = res,
                2 if s.read_res >= 0 => s.read_res = res,
                _ => {}
            }
            s.left -= 1;
            if s.left == 0 {
                let mut s = slots[i].take().unwrap();
                inflight -= 1;
                let want = k.min(s.job.size as usize);
                let data = (s.read_res >= 0).then(|| s.buf.slice()[..(s.read_res as usize).min(want)].to_vec());
                let m = decide(&db, std::mem::take(&mut s.job.cands), data.as_deref());
                let rel = s.job.path.strip_prefix(&root).unwrap().to_string_lossy().into_owned();
                results.lock().unwrap().push((rel, m));
                queue.done();
            }
        }
    }
}

fn main() {
    let o = parse_args();
    let db = Arc::new(SharedMimeInfo::new_for_directory(&o.mimedb)); // reads DIR/mime
    let k = if o.bytes > 0 { o.bytes } else { 18730 }; // pyxdg's Mime.magic.maxlen for this database
    let root = std::fs::canonicalize(&o.root).unwrap();
    let queue = Arc::new(Queue { state: Mutex::new((VecDeque::new(), 0)), cv: Condvar::new() });
    let results: Results = Arc::new(Mutex::new(Vec::new()));
    let counts = Arc::new(Mutex::new((0usize, 0usize, 0usize))); // dirs, files, read
    let t0 = Instant::now();
    queue.push(Task::Dir(root.clone()));

    let (tx, rx) = mpsc::channel::<Job>();
    let ring = (o.uring > 0).then(|| {
        let (db, root, results, queue) = (db.clone(), root.clone(), results.clone(), queue.clone());
        let (depth, mode) = (o.uring, o.read);
        std::thread::spawn(move || ring_thread(rx, depth, k, mode, db, root, results, queue))
    });

    let workers: Vec<_> = (0..o.threads)
        .map(|_| {
            let (queue, db, root, results, counts) =
                (queue.clone(), db.clone(), root.clone(), results.clone(), counts.clone());
            let tx = (o.uring > 0).then(|| tx.clone());
            let (mode, defer_stat) = (o.read, o.defer_stat);
            std::thread::spawn(move || {
                while let Some(task) = queue.pop() {
                    match task {
                        Task::Dir(p) => {
                            let mut names: Vec<_> = match std::fs::read_dir(&p) {
                                Ok(it) => it.filter_map(|e| e.ok()).collect(),
                                Err(e) => {
                                    eprintln!("{}: {e}", p.display());
                                    Vec::new()
                                }
                            };
                            names.sort_by_key(|e| e.file_name());
                            for e in names {
                                if defer_stat {
                                    // d_type from READDIR; the lstat happens in the file's own task
                                    let Ok(ft) = e.file_type() else { continue };
                                    if ft.is_dir() {
                                        queue.push(Task::Dir(e.path()));
                                    } else if ft.is_file() {
                                        queue.push(Task::File(e.path(), u64::MAX));
                                    }
                                    continue;
                                }
                                let Ok(md) = e.metadata() else { continue }; // lstat
                                if md.is_dir() {
                                    queue.push(Task::Dir(e.path()));
                                } else if md.is_file() {
                                    queue.push(Task::File(e.path(), md.len()));
                                }
                            }
                            counts.lock().unwrap().0 += 1;
                        }
                        Task::File(p, size) => {
                            let name = p.file_name().unwrap().to_string_lossy().into_owned();
                            let cands = glob_candidates(&db, &name);
                            let needs_read = cands.len() != 1;
                            // A file that is opened anyway gets its attributes by fstat
                            // (from OPEN's reply) in read_header; the others by lstat here.
                            let size = if size == u64::MAX && !(needs_read && tx.is_none()) {
                                match std::fs::symlink_metadata(&p) {
                                    Ok(md) => md.len(),
                                    Err(_) => {
                                        queue.done();
                                        continue;
                                    }
                                }
                            } else {
                                size
                            };
                            {
                                let mut c = counts.lock().unwrap();
                                c.1 += 1;
                                c.2 += needs_read as usize;
                            }
                            if needs_read && let Some(tx) = &tx {
                                tx.send(Job { path: p, size, cands }).unwrap();
                                continue; // the ring thread finishes the task
                            }
                            let m = if needs_read {
                                let data = read_header(&p, size, k, mode).ok();
                                decide(&db, cands, data.as_deref())
                            } else {
                                cands[0].clone()
                            };
                            let rel = p.strip_prefix(&root).unwrap().to_string_lossy().into_owned();
                            results.lock().unwrap().push((rel, m));
                        }
                    }
                    queue.done();
                }
            })
        })
        .collect();
    drop(tx);
    for w in workers {
        w.join().unwrap();
    }
    if let Some(r) = ring {
        r.join().unwrap();
    }
    let wall = t0.elapsed().as_secs_f64();
    let ru = unsafe {
        let mut ru: libc::rusage = std::mem::zeroed();
        libc::getrusage(libc::RUSAGE_SELF, &mut ru);
        ru
    };
    let c = counts.lock().unwrap();
    let tv = |t: libc::timeval| t.tv_sec as f64 + t.tv_usec as f64 / 1e6;
    eprintln!(
        "threads {} uring {} read {}: {} dirs, {} files, {} read, {:.2} s, {:.1} files/s, cpu user {:.2} s sys {:.2} s, maxrss {} MB",
        o.threads,
        o.uring,
        ["plain", "fadvise", "odirect"][o.read as usize],
        c.0,
        c.1,
        c.2,
        wall,
        c.1 as f64 / wall,
        tv(ru.ru_utime),
        tv(ru.ru_stime),
        ru.ru_maxrss / 1024
    );
    if let Some(out) = o.out {
        let mut r = results.lock().unwrap();
        r.sort();
        let mut f = std::io::BufWriter::new(std::fs::File::create(out).unwrap());
        for (rel, m) in r.iter() {
            writeln!(f, "/{rel}\t{m}").unwrap();
        }
    }
}
