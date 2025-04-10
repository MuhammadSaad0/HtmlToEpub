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
    def __init__(self, html_file, author_name, book_title, language="en-US", 
                 release_year=None, work_type="novel", subjects=None):
        self.html_file = html_file
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
        """Find the Standard Ebooks executable path."""
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
        """Load and parse the Project Gutenberg HTML file."""
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
    
    def clean_gutenberg_html(self):
        """Remove Project Gutenberg header, footer, and clean up the HTML."""
        print("Cleaning up Project Gutenberg HTML...")
        
        if not self.soup:
            print("HTML not loaded. Run load_html() first.")
            return False
        
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
        """Identify and structure chapter content."""
        print("Identifying chapters...")
        
        chapter_patterns = [
            'h1', 'h2', 'h3',
            'div[class*=chapter]', 'div[id*=chapter]',
            'span[class*=chapter]', 'span[id*=chapter]',
            '.chapter', '#chapter'
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
        """Convert a name to SE-friendly format."""
        name = name.lower()
        name = name.replace(' ', '-')
        name = re.sub(r'[^a-z0-9-]', '', name)
        name = re.sub(r'-+', '-', name)
        return name
    
    def create_standard_ebooks_project(self):
        """Create a new Standard Ebooks project."""
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
        """Generate Standard Ebooks XHTML files for each chapter."""
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
            
            content_soup = BeautifulSoup(chapter['content'], 'html.parser')
            
            for header in content_soup.find_all(['h1', 'h2', 'h3', 'h4']):
                if header.get_text().strip() == title:
                    header.decompose()
                    break
            
            content = str(content_soup)
            
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
            
            file_path = os.path.join(text_dir, file_name)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(xhtml_content)
            
            print(f"Created chapter file: {file_name}")
            
            toc_xhtml.append((file_name, title))
        
        self._update_toc(toc_xhtml)
        
        return True
    
    def _update_toc(self, toc_entries):
        """Update the table of contents file."""
        toc_path = os.path.join(self.project_dir, "src", "epub", "toc.xhtml")
        
        with open(toc_path, 'r', encoding='utf-8') as f:
            toc_content = f.read()
        
        parser = etree.XMLParser(remove_blank_text=True)
        root = etree.fromstring(toc_content.encode('utf-8'), parser)
        
        namespace = {
            "xhtml": "http://www.w3.org/1999/xhtml",
            "epub": "http://www.idpf.org/2007/ops"  # Add the epub namespace
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
        """Update the content.opf metadata file."""
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
        """Run Standard Ebooks commands to process the files."""
        if not self.project_dir:
            print("Project not initialized.")
            return False
        
        original_dir = os.getcwd()
        
        try:
            os.chdir(self.project_dir)
            
            print("Running Standard Ebooks commands...")
            
            print("Running 'se prepare'...")
            subprocess.run([self.se_path, "prepare-release", "."], check=True)
            
            print("Running 'se build'...")
            subprocess.run([self.se_path, "build", "."], check=True)
            
            print("Running 'se lint'...")
            subprocess.run([self.se_path, "lint", "."], check=False)  # Don't fail on lint errors
            
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error running Standard Ebooks command: {e}")
            return False
        finally:
            os.chdir(original_dir)
    
    def convert(self):
        """Run the full conversion process."""
        if not self.load_html():
            return False
        
        if not self.clean_gutenberg_html():
            return False
        
        self.identify_chapters()
        
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
    parser = argparse.ArgumentParser(description='Convert Project Gutenberg HTML to Standard Ebooks format')
    parser.add_argument('html_file', help='Path or URL to the Project Gutenberg HTML file')
    parser.add_argument('author', help='Author name in format "Firstname Lastname"')
    parser.add_argument('title', help='Book title')
    parser.add_argument('--language', default='en-US', help='Language code (default: en-US)')
    parser.add_argument('--year', type=int, help='Original publication year')
    parser.add_argument('--type', default='novel', choices=['novel', 'short-story', 'novella', 'anthology', 'non-fiction'],
                        help='Work type (default: novel)')
    parser.add_argument('--subjects', nargs='+', help='Subject tags (e.g., "Fiction" "Romance")')
    
    args = parser.parse_args()
    
    converter = GutenbergToStandardEbooks(
        html_file=args.html_file,
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