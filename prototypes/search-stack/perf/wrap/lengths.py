"""Token lengths of the VM's real events' embedding texts: runs batch-memory.py on N events, then reads its texts."""

import runpy
import sys

n = sys.argv[1]
sys.argv = ["x", n, "0", "1", "0"]
g = runpy.run_path("/probe/batch-memory.py", run_name="__main__")
tok = g["resources"].embedding_transformer.model.tokenizer
tok.no_padding()
lengths = [len(tok.encode(x).ids) for x in g["texts"]]
print("tokens per text, in batch order:", lengths)
