# Spec Delta

## ADDED Requirements

### Requirement: Detection can leave a type out
Detection SHALL be able to leave one type out (spec `recognition`, a dropped name type) and follow the checking order without it: the remaining name rules decide, and a content match of the left-out type SHALL count as no match. Only the best content match is considered, so a weaker one is lost. Asked to, detection SHALL raise a read error instead of falling back to `application/octet-stream`.

#### Scenario: A weaker name rule decides
- **WHEN** a file named `README.png` holding `hello\n` is classified with `image/png` left out
- **THEN** its type is `text/x-readme`, the type of the weaker name rule `README*`, without its content being read

#### Scenario: The content matches the left-out type
- **WHEN** a file named `x.png` starting with the PNG signature is classified with `image/png` left out
- **THEN** its type is `application/octet-stream`: no name rule is left, the content match is the left-out type, and the bytes do not look like text

#### Scenario: No rule left, the content decides
- **WHEN** a file named `notes.png` holding `hello\n` is classified with `image/png` left out
- **THEN** its type is `text/plain`

#### Scenario: A read error is raised when asked
- **WHEN** a file named `notes.png` cannot be read and is classified with `image/png` left out, asking for read errors to be raised
- **THEN** detection raises the read error
