# Gutenberg to Standard Ebooks Converter

Convert [Project Gutenberg](https://www.gutenberg.org/) HTML or custom Markdown files into a ready-to-edit [Standard Ebooks](https://standardebooks.org) project.

---

##  Features

- Parse and clean up Gutenberg HTML or Markdown
- Create a fully structured Standard Ebooks project
- Auto-generate chapter XHTML files
- Inject metadata, update `content.opf`, and regenerate ToC
- Run `se prepare-release`, `se build`, and `se lint`

---

##  Docker Usage

```
docker build -t gutenberg-to-se .
```
### HTML input
```
docker run --rm -v $(pwd):/data gutenberg-to-se \
  --html /data/test.html "Author Name" "Book Title"
```
### Markdown input
```
docker run --rm -v $(pwd):/data gutenberg-to-se \
  --markdown /data/book.md "Author Name" "Book Title"
```

Script Usage (Without Docker)
```
python script.py (--html HTML | --markdown MARKDOWN) author title
                 [--language LANGUAGE]
                 [--year YEAR]
                 [--type {novel,short-story,novella,anthology,non-fiction}]
                 [--subjects SUBJECTS [SUBJECTS ...]]

```
