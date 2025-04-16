#!/usr/bin/env python3

import os
import re
import sys
import subprocess
import argparse
import shutil
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup
import requests
from lxml import etree

class GutenbergToStandardEbooks:
    def __init__(self, html_file=None, markdown_file=None, author_name=None, book_title=None, 
                 language="en-US", release_year=None, work_type="novel", subjects=None):
        self.html_file = html_file
        self.markdown_file = markdown_file
        self.author_name = author_name
        self.book_title = book_title
        self.language = language
        self.release_year = release_year or datetime.now().year
        self.work_type = work_type
        self.subjects = subjects or []
        self.project_dir = None
        self.soup = None
        self.chapters = []
        self.se_path = self._find_se_executable()
        
    def _find_se_executable(self):
        possible_paths = [
            "se",
            os.path.expanduser("~/standardebooks/tools/se"),
            os.path.expanduser("~/tools/se"),
            os.path.expanduser("~/se"),
            "/usr/local/bin/se",
        ]
        
        for path in possible_paths:
            try:
                subprocess.run([path, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                return path
            except (FileNotFoundError, subprocess.SubprocessError):
                continue
                
        print("ERROR: Could not find the Standard Ebooks 'se' command.")
        print("Please install it from https://github.com/standardebooks/tools")
        sys.exit(1)
    
    def load_html(self):
        if not self.html_file:
            return False
            
        print(f"Loading HTML from {self.html_file}...")
        
        try:
            if self.html_file.startswith(('http://', 'https://')):
                response = requests.get(self.html_file)
                html_content = response.text
            else:
                with open(self.html_file, 'r', encoding='utf-8') as file:
                    html_content = file.read()
            
            self.soup = BeautifulSoup(html_content, 'html.parser')
            return True
        except Exception as e:
            print(f"Error loading HTML: {e}")
            return False
    
    def load_markdown(self):
        if not self.markdown_file:
            return False
            
        print(f"Loading markdown from {self.markdown_file}...")
        
        try:
            with open(self.markdown_file, 'r', encoding='utf-8') as file:
                markdown_content = file.read()
            
            chapter_pattern = re.compile(r'##\s+(.*?)(?=##|\Z)', re.DOTALL)
            
            chapter_matches = chapter_pattern.findall(markdown_content)
            
            if not chapter_matches:
                print("No chapters found in the markdown file.")
                return False
                
            self.chapters = []
            
            for chapter_text in chapter_matches:
                lines = chapter_text.strip().split('\n', 1)
                chapter_title = lines[0].strip()
                
                chapter_content = lines[1].strip() if len(lines) > 1 else ""
                
                html_content = self._markdown_to_html(chapter_content)
                
                self.chapters.append({
                    'title': chapter_title,
                    'content': html_content
                })
            
            print(f"Successfully parsed {len(self.chapters)} chapters from markdown.")
            return True
            
        except Exception as e:
            print(f"Error loading markdown: {e}")
            return False
    
    def _markdown_to_html(self, markdown_text):
        try:
            wrapped_content = f"<div>{markdown_text}</div>"
            soup = BeautifulSoup(wrapped_content, 'html.parser')
            
            return ''.join(str(tag) for tag in soup.div.contents)
        except Exception as e:
            print(f"Warning: Error formatting HTML content: {e}")
            print("Falling back to basic content")
            return f"<p>{markdown_text}</p>"
    
    def clean_gutenberg_html(self):
        if not self.html_file or not self.soup:
            return True  
            
        print("Cleaning up Project Gutenberg HTML...")
        
        header_patterns = [
            re.compile(r'The Project Gutenberg eBook.*?produced by', re.DOTALL | re.IGNORECASE),
            re.compile(r'Project Gutenberg.*?START OF (THIS|THE) PROJECT GUTENBERG', re.DOTALL | re.IGNORECASE),
        ]
        
        content = str(self.soup)
        for pattern in header_patterns:
            content = pattern.sub('', content)
        
        footer_patterns = [
            re.compile(r'End of (the |)Project Gutenberg.*', re.DOTALL | re.IGNORECASE),
            re.compile(r'This file should be named.*?gutenberg.org', re.DOTALL | re.IGNORECASE),
        ]
        
        for pattern in footer_patterns:
            content = pattern.sub('', content)
        
        self.soup = BeautifulSoup(content, 'html.parser')
        
        for element in self.soup.select('.pgheader, .pgfooter, #pg-header, #pg-footer'):
            element.decompose()
        
        for element in self.soup.find_all(['script', 'style']):
            element.decompose()
        
        return True
    
    def identify_chapters(self):
        if self.markdown_file or self.chapters:
            return True
            
        print("Identifying chapters...")
        
        chapter_patterns = [
            'h1', 'h2', 'h3',
            'div[class*=chapter]', 'div[id*=chapter]',
            'span[class*=chapter]', 'span[id*=chapter]',
            '.chapter', '#chapter',
            '##'
        ]
        
        potential_chapters = []
        for pattern in chapter_patterns:
            potential_chapters.extend(self.soup.select(pattern))
        
        if not potential_chapters:
            print("WARNING: Could not automatically identify chapters.")
            print("Treating entire document as a single chapter.")
            self.chapters = [{
                'title': 'Chapter 1',
                'content': str(self.soup.body)
            }]
            return
        
        potential_chapters.sort(key=lambda x: str(x).find(str(x)))
        
        current_title = "Introduction"
        current_content = []
        
        if potential_chapters and potential_chapters[0].get_text().strip().lower() in ['title page', 'title', self.book_title.lower()]:
            current_title = potential_chapters[0].get_text().strip()
            potential_chapters = potential_chapters[1:]
        
        for i, chapter_marker in enumerate(potential_chapters):
            if current_content:
                chapter_content = ''.join(str(c) for c in current_content)
                self.chapters.append({
                    'title': current_title,
                    'content': chapter_content
                })
            
            current_title = chapter_marker.get_text().strip()
            current_content = []
            
            next_element = chapter_marker.next_sibling
            while next_element and (i == len(potential_chapters) - 1 or next_element != potential_chapters[i+1]):
                if next_element.name:  
                    current_content.append(next_element)
                next_element = next_element.next_sibling
                if not next_element:
                    break
        
        if current_content:
            chapter_content = ''.join(str(c) for c in current_content)
            self.chapters.append({
                'title': current_title,
                'content': chapter_content
            })
        
        print(f"Identified {len(self.chapters)} chapters.")
    
    def _make_se_friendly_name(self, name):
        name = name.lower()
        name = name.replace(' ', '-')
        name = re.sub(r'[^a-z0-9-]', '', name)
        name = re.sub(r'-+', '-', name)
        return name
    
    def create_standard_ebooks_project(self):
        print(f"Creating Standard Ebooks project for '{self.book_title}' by {self.author_name}...")
        
        cmd = [
            self.se_path, 
            "create-draft", 
            "-a", self.author_name,
            "-t", self.book_title
        ]
        
        print(f"Running command: {' '.join(cmd)}")
        
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        
        print("\nCommand Output:")
        print(process.stdout)
        
        if process.stderr:
            print("\nCommand Error Output:")
            print(process.stderr)
        
        if process.returncode != 0:
            print(f"Error creating Standard Ebooks project. Return code: {process.returncode}")
            return False
        
        output = process.stdout
        match = re.search(r'Created project directory at (.*)', output)
        
        if match:
            self.project_dir = match.group(1).strip()
            print(f"Project created at: {self.project_dir}")
            return True
        else:
            print("Could not determine project directory from output, attempting to guess...")
            
            author_name_se = self._make_se_friendly_name(self.author_name)
            title_se = self._make_se_friendly_name(self.book_title)
            
            possible_dirs = [
                f"{author_name_se}_{title_se}",
                f"{title_se}",
                os.path.join(os.getcwd(), f"{author_name_se}_{title_se}")
            ]
            
            for dir_path in possible_dirs:
                if os.path.isdir(dir_path):
                    self.project_dir = dir_path
                    print(f"Found project directory at: {self.project_dir}")
                    return True
            
            current_dir = os.getcwd()
            dirs_before = set(os.listdir(current_dir))
            
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            
            dirs_after = set(os.listdir(current_dir))
            new_dirs = dirs_after - dirs_before
            
            if new_dirs:
                newest_dir = max([os.path.join(current_dir, d) for d in new_dirs], 
                                key=os.path.getctime)
                self.project_dir = newest_dir
                print(f"Found newly created project directory at: {self.project_dir}")
                return True
            
            print("Failed to find project directory. Please check Standard Ebooks output manually.")
            print("You may need to create the project directory manually and specify it directly.")
            return False
    
    def generate_chapter_files(self):
        if not self.project_dir or not self.chapters:
            print("Project not initialized or chapters not identified.")
            return False
        
        print("Generating chapter files...")
        
        text_dir = os.path.join(self.project_dir, "src", "epub", "text")
        os.makedirs(text_dir, exist_ok=True)
        
        xhtml_template = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" epub:prefix="z3998: http://www.daisy.org/z3998/2012/vocab/structure/, se: https://standardebooks.org/vocab/1.0" xml:lang="{language}">
<head>
    <title>{title}</title>
    <link href="../css/core.css" rel="stylesheet" type="text/css"/>
    <link href="../css/local.css" rel="stylesheet" type="text/css"/>
</head>
<body epub:type="bodymatter z3998:fiction">
    <section id="{id}" epub:type="chapter">
        <h2 epub:type="title">{title}</h2>
        {content}
    </section>
</body>
</html>"""
        
        toc_xhtml = []
        for i, chapter in enumerate(self.chapters, 1):
            title = chapter['title'].strip()
            if not title:
                title = f"Chapter {i}"
                
            roman_match = re.match(r'^chapter\s+([IVXLCDM]+)$', title.lower())
            if roman_match:
                title = f"Chapter {roman_match.group(1)}"
            
            content = chapter['content']
            
            try:
                if isinstance(content, BeautifulSoup):
                    content_soup = content
                else:
                    content_soup = BeautifulSoup(f"<div>{content}</div>", 'html.parser')
                    
                if hasattr(content_soup, 'div'):
                    content = ''.join(str(tag) for tag in content_soup.div.contents)
                else:
                    content = str(content_soup)
                    
                for header in content_soup.find_all(['h1', 'h2', 'h3', 'h4']):
                    if header.get_text().strip() == title:
                        header.decompose()
                
                if hasattr(content_soup, 'div'):
                    content = ''.join(str(tag) for tag in content_soup.div.contents)
                else:
                    content = str(content_soup)
                    
            except Exception as e:
                print(f"Warning: Error parsing chapter {i} content: {e}")
                content = f"<p>{content}</p>"
            
            content = content.replace('"', '"').replace('"', '"')
            content = content.replace("'", "'").replace("'", "'")
            content = content.replace("--", "—")
            
            file_id = f"chapter-{i}"
            file_name = f"{file_id}.xhtml"
            
            xhtml_content = xhtml_template.format(
                language=self.language,
                title=title,
                id=file_id,
                content=content
            )
            
            try:
                etree.fromstring(xhtml_content.encode('utf-8'))
            except etree.XMLSyntaxError as e:
                print(f"Warning: XML syntax error in chapter {i}. Attempting to fix...")
                content = self._fix_xml_issues(content)
                xhtml_content = xhtml_template.format(
                    language=self.language,
                    title=title,
                    id=file_id,
                    content=content
                )
                
                try:
                    etree.fromstring(xhtml_content.encode('utf-8'))
                    print(f"Successfully fixed XML for chapter {i}")
                except etree.XMLSyntaxError as e:
                    print(f"Error: Could not fix XML for chapter {i}. Using basic content instead.")
                    content = f"<p>Chapter content unavailable due to XML errors: {e}</p>"
                    xhtml_content = xhtml_template.format(
                        language=self.language,
                        title=title,
                        id=file_id,
                        content=content
                    )
            
            file_path = os.path.join(text_dir, file_name)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(xhtml_content)
            
            print(f"Created chapter file: {file_name}")
            
            toc_xhtml.append((file_name, title))
        
        self._update_toc(toc_xhtml)
        
        return True
    
    def _fix_xml_issues(self, content):
        soup = BeautifulSoup(f"<div>{content}</div>", 'html.parser')
        clean_content = ''.join(str(tag) for tag in soup.div.contents)
        
        clean_content = clean_content.replace('&', '&amp;')
        clean_content = re.sub(r'&amp;([a-zA-Z]+);', r'&\1;', clean_content)   
        
        clean_content = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', clean_content)
        
        return clean_content
    
    def _update_toc(self, toc_entries):
        toc_path = os.path.join(self.project_dir, "src", "epub", "toc.xhtml")
        
        with open(toc_path, 'r', encoding='utf-8') as f:
            toc_content = f.read()
        
        parser = etree.XMLParser(remove_blank_text=True)
        root = etree.fromstring(toc_content.encode('utf-8'), parser)
        
        namespace = {
            "xhtml": "http://www.w3.org/1999/xhtml",
            "epub": "http://www.idpf.org/2007/ops" 
        }
        nav = root.find(".//xhtml:nav[@epub:type='toc']", namespaces=namespace)
        
        if nav is not None:
            ol = nav.find(".//xhtml:ol", namespaces=namespace)
            if ol is not None:
                ol.clear()
            else:
                ol = etree.SubElement(nav, "{http://www.w3.org/1999/xhtml}ol")
        else:
            print("ERROR: Could not find TOC nav element")
            return False
        
        for file_name, title in toc_entries:
            li = etree.SubElement(ol, "{http://www.w3.org/1999/xhtml}li")
            a = etree.SubElement(li, "{http://www.w3.org/1999/xhtml}a")
            a.set("href", f"text/{file_name}")
            a.text = title
        
        with open(toc_path, 'wb') as f:
            f.write(etree.tostring(root, pretty_print=True, xml_declaration=True, encoding='utf-8'))
        
        print(f"Updated table of contents with {len(toc_entries)} entries.")
        return True
    
    def update_content_opf(self):
        opf_path = os.path.join(self.project_dir, "src", "epub", "content.opf")
        
        try:
            with open(opf_path, 'r', encoding='utf-8') as f:
                opf_content = f.read()
        except FileNotFoundError:
            print(f"OPF file not found at {opf_path}")
            return False
        
        parser = etree.XMLParser(remove_blank_text=True)
        root = etree.fromstring(opf_content.encode('utf-8'), parser)
        
        ns = {
            "opf": "http://www.idpf.org/2007/opf",
            "dc": "http://purl.org/dc/elements/1.1/"
        }
        
        lang_elem = root.find(".//dc:language", namespaces=ns)
        if lang_elem is not None:
            lang_elem.text = self.language
        
        if self.subjects:
            for subject in self.subjects:
                subject_elem = etree.SubElement(root.find(".//opf:metadata", namespaces=ns), 
                                             "{http://purl.org/dc/elements/1.1/}subject")
                subject_elem.text = subject
        
        manifest = root.find(".//opf:manifest", namespaces=ns)
        spine = root.find(".//opf:spine", namespaces=ns)
        
        if manifest is None or spine is None:
            print("Could not find manifest or spine elements in content.opf")
            return False
        
        existing_ids = [item.get("id") for item in manifest.findall("opf:item", namespaces=ns)]
        existing_idrefs = [item.get("idref") for item in spine.findall("opf:itemref", namespaces=ns)]
        
        for i in range(1, len(self.chapters) + 1):
            item_id = f"chapter-{i}"
            href = f"text/chapter-{i}.xhtml"
            
            if item_id not in existing_ids:
                item = etree.SubElement(manifest, "{http://www.idpf.org/2007/opf}item")
                item.set("id", item_id)
                item.set("href", href)
                item.set("media-type", "application/xhtml+xml")
            
            if item_id not in existing_idrefs:
                itemref = etree.SubElement(spine, "{http://www.idpf.org/2007/opf}itemref")
                itemref.set("idref", item_id)
        
        with open(opf_path, 'wb') as f:
            f.write(etree.tostring(root, pretty_print=True, xml_declaration=True, encoding='utf-8'))
        
        print("Updated content.opf metadata file.")
        return True
    
    def run_se_commands(self):
        if not self.project_dir:
            print("Project not initialized.")
            return False
        
        original_dir = os.getcwd()
        
        try:
            os.chdir(self.project_dir)
            
            print("Running Standard Ebooks commands...")
            
            print("Running 'se prepare'...")
            prepare_result = subprocess.run(
                [self.se_path, "prepare-release", "."], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )
            
            if prepare_result.returncode != 0:
                print("Warning: 'se prepare' command returned errors:")
                print(prepare_result.stderr)
                print("Attempting to continue with build...")
            
            print("Running 'se build'...")
            build_result = subprocess.run(
                [self.se_path, "build", "."], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )
            
            if build_result.returncode != 0:
                print("Warning: 'se build' command returned errors:")
                print(build_result.stderr)
                print("Final epub may have issues.")
            
            print("Running 'se lint'...")
            lint_result = subprocess.run(
                [self.se_path, "lint", "."], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )
            
            if lint_result.returncode != 0:
                print("Note: 'se lint' reported issues that should be fixed:")
                print(lint_result.stdout)
            
            return True
        except Exception as e:
            print(f"Error running Standard Ebooks command: {e}")
            return False
        finally:
            os.chdir(original_dir)
    
    def convert(self):
        content_loaded = False
        
        if self.markdown_file and self.load_markdown():
            content_loaded = True
        elif self.html_file and self.load_html():
            if not self.clean_gutenberg_html():
                return False
            self.identify_chapters()
            content_loaded = True
        
        if not content_loaded:
            print("No content loaded. Please provide either a markdown or HTML file.")
            return False
        
        if not self.create_standard_ebooks_project():
            print("\nAutomatic project directory detection failed.")
            user_dir = input("Please enter the path to the Standard Ebooks project directory: ")
            if user_dir and os.path.isdir(user_dir):
                self.project_dir = os.path.abspath(user_dir)
                print(f"Using manually specified project directory: {self.project_dir}")
            else:
                print("Invalid directory path. Aborting.")
                return False
        
        if not self.generate_chapter_files():
            return False
        
        if not self.update_content_opf():
            return False
        
        if not self.run_se_commands():
            return False
        
        print("\nConversion completed!")
        print(f"Project created at: {self.project_dir}")
        print("\nNote: You'll still need to:")
        print("1. Review and correct any issues reported by 'se lint'")
        print("2. Add proper cover art")
        print("3. Complete any missing metadata")
        print("4. Verify the final EPUB")
        
        return True


def main():
    parser = argparse.ArgumentParser(description='Convert Project Gutenberg HTML or markdown to Standard Ebooks format')
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument('--html', help='Path or URL to the Project Gutenberg HTML file')
    input_group.add_argument('--markdown', help='Path to a markdown file with chapter format')
    
    parser.add_argument('author', help='Author name in format "Firstname Lastname"')
    parser.add_argument('title', help='Book title')
    parser.add_argument('--language', default='en-US', help='Language code (default: en-US)')
    parser.add_argument('--year', type=int, help='Original publication year')
    parser.add_argument('--type', default='novel', choices=['novel', 'short-story', 'novella', 'anthology', 'non-fiction'],
                      help='Work type (default: novel)')
    parser.add_argument('--subjects', nargs='+', help='Subject tags (e.g., "Fiction" "Romance")')
    
    args = parser.parse_args()
    
    converter = GutenbergToStandardEbooks(
        html_file=args.html,
        markdown_file=args.markdown,
        author_name=args.author,
        book_title=args.title,
        language=args.language,
        release_year=args.year,
        work_type=args.type,
        subjects=args.subjects
    )
    
    converter.convert()


if __name__ == "__main__":
    main()