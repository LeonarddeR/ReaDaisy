# daisy-extract
# Copyright (C) 2016-2014 James Scholes, Leonard de Ruijter
# This program is free software, licensed under the terms of the
# GNU General Public License (version 3 or later).
# See the file LICENSE for more details.

import argparse
import os
import shutil
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from functools import cached_property
from glob import glob
from typing import Self

from bs4 import BeautifulSoup
from reathon.nodes import Item, Project, Source, Track

NCC_FILENAME = "NCC.HTML"


@dataclass
class Smil:
    """Represents a SMIL document in a DAISY book."""

    level: int
    title: str
    file_name: str
    children: list[Self] = field(default_factory=list)


@dataclass
class Segment:
    identifier: str
    start: Decimal
    end: Decimal

    @cached_property
    def length(self) -> Decimal:
        return self.end - self.start


@dataclass
class Audio:
    file_name: str
    start: Decimal
    length: Decimal
    segments: list[Segment] = field(default_factory=list)

    @cached_property
    def end(self) -> Decimal:
        return self.start + self.length


def main():
    """Main function to process DAISY books."""
    cli_args = parse_command_line()
    input_directory = os.path.abspath(cli_args.input_directory)
    output_directory = os.path.abspath(cli_args.output_directory)

    if not os.path.exists(input_directory) or not os.path.isdir(input_directory):
        exit_with_error(f"{input_directory} does not exist or is not a directory")

    ncc_files = glob(os.path.join(input_directory, "**", NCC_FILENAME), recursive=True)
    book_start_number = 1

    for ncc_file in ncc_files:
        ncc_dir = os.path.dirname(ncc_file)
        smils = get_smils(ncc_file)
        for index, book in enumerate(smils, start=book_start_number):
            book_name = f"{index:02d} - {book.title}"
            book_dir = os.path.join(output_directory, book_name)
            os.makedirs(book_dir, exist_ok=True)

            audio_list = process_book(book, ncc_dir, book_dir)

            create_reaper_project(
                audio_list,
                os.path.join(book_dir, f"{book.title}.RPP"),
                book.title,
            )
        book_start_number += len(smils)


def copy_audio_file(
    input_directory: str,
    book_dir: str,
    current_file_name: str,
    new_filename: str,
):
    """Copy audio file from input directory to book directory."""
    source_path = os.path.join(input_directory, current_file_name)
    destination_path = os.path.join(book_dir, new_filename)
    shutil.copy2(source_path, destination_path)


def create_reaper_project(
    audio_list: list[Audio],
    output_path: str,
    title: str,
) -> None:
    """
    Creates a Reaper project file from a list of audio files.
    """
    project = Project(timemode=3, timelockmode=1)
    track = Track(name=f'"{title}"')
    project.add(track)
    marker_index = 1
    for audio in audio_list:
        source = Source(file=audio.file_name)
        item = Item(
            source,
            name=f'"{os.path.splitext(audio.file_name)[0]}"',
            position=audio.start,
            length=audio.length,
        )
        track.add(item)
        for segment in audio.segments:
            project.add_marker(marker_index, float(segment.start), segment.identifier)
            marker_index += 1

    project.write(output_path)


def process_book(
    book: Smil,
    input_directory: str,
    output_directory: str,
) -> list[Audio]:
    """
    Process a book by extracting audio metadata from its SMIL content,
    copying the audio files to an output directory,
    and creating a Reaper project file for the book.
    """
    smil_path = os.path.join(input_directory, book.file_name)
    smil_content = parse_smil_document(smil_path)
    total_chapters = len(book.children)
    chapter_padding = len(str(total_chapters))
    book_prefix = f"{str(0).zfill(chapter_padding)} - {book.title}"
    audio = get_audio(smil_content, 0, book_prefix)
    audio_files = [
        audio,
    ]
    book_start = get_start_time(smil_content)

    new_file_name = make_safe_filename(
        f"{book_prefix}{os.path.splitext(audio.file_name)[1]}"
    )
    copy_audio_file(input_directory, output_directory, audio.file_name, new_file_name)
    audio.file_name = new_file_name

    for i, chapter in enumerate(book.children, start=1):
        audio_files.extend(
            process_chapter(
                chapter,
                i,
                input_directory,
                output_directory,
                book_start,
                chapter_padding,
            )
        )

    return audio_files


def process_chapter(
    chapter: Smil,
    index: int,
    input_directory: str,
    book_dir: str,
    book_start: Decimal,
    chapter_padding: int,
) -> list[Audio]:
    """Process a chapter within a book."""
    smil_path = os.path.join(input_directory, chapter.file_name)
    smil_content = parse_smil_document(smil_path)
    rel_start = get_start_time(smil_content) - book_start
    total_subheadings = len(chapter.children)
    subheading_padding = len(str(total_subheadings))
    chapter_prefix = (chapter.title if chapter.title.isdigit() else str(index)).zfill(
        chapter_padding
    )
    audio = get_audio(smil_content, rel_start, chapter_prefix)
    chapter_audio_files = [
        audio,
    ]

    new_file_name = make_safe_filename(
        f"{chapter_prefix} - {str(0).zfill(subheading_padding)}"
        f"{os.path.splitext(audio.file_name)[1]}"
    )
    copy_audio_file(input_directory, book_dir, audio.file_name, new_file_name)
    audio.file_name = new_file_name
    for subheading_index, subheading in enumerate(chapter.children, start=1):
        chapter_audio_files.append(
            process_subheading(
                subheading,
                input_directory,
                book_dir,
                book_start,
                str(subheading_index).zfill(subheading_padding),
                chapter_prefix,
            )
        )

    return chapter_audio_files


def process_subheading(
    subheading: Smil,
    input_directory: str,
    book_dir: str,
    book_start: Decimal,
    subheading_index: str,
    chapter_prefix: str,
) -> Audio:
    """Process a subheading within a chapter."""
    smil_path = os.path.join(input_directory, subheading.file_name)
    smil_content = parse_smil_document(smil_path)
    rel_start = get_start_time(smil_content) - book_start
    subheading_prefix = f"{chapter_prefix} - {subheading_index} - {subheading.title}"
    audio = get_audio(smil_content, rel_start, subheading_prefix)
    subheading_new_file_name = make_safe_filename(
        f"{subheading_prefix}{os.path.splitext(audio.file_name)[1]}"
    )
    copy_audio_file(
        input_directory,
        book_dir,
        audio.file_name,
        subheading_new_file_name,
    )
    audio.file_name = subheading_new_file_name
    return audio


def parse_smil_document(smil_path: str) -> BeautifulSoup:
    """Parse a SMIL document and return a BeautifulSoup object."""
    with open(smil_path, encoding="utf-8") as f:
        return BeautifulSoup(f, "xml")


def get_start_time(smil_content: BeautifulSoup) -> Decimal:
    """Extract the start time from a SMIL document."""
    meta_tag = smil_content.find("meta", attrs={"name": "ncc:totalElapsedTime"})
    if not meta_tag:
        raise RuntimeError("No meta tag found")

    time_str = meta_tag["content"]
    parts = time_str.split(":")
    return sum(Decimal(part) * (60**i) for i, part in enumerate(reversed(parts)))


def get_audio(
    smil_content: BeautifulSoup,
    start_time: Decimal = Decimal(0),
    id_prefix: str = "",
) -> Audio:
    seq_tag = smil_content.find("seq", dur=True)
    duration = Decimal(seq_tag["dur"][:-1])  # Remove 's' and convert to Decimal
    audio_tags = seq_tag.find_all("audio")
    file_name = audio_tags[0]["src"]
    audio = Audio(file_name, start_time, duration)

    for audio_tag in audio_tags:
        identifier = f"{id_prefix} - {int(audio_tag["id"].split("_")[-1], base=16)}"
        seg_start = Decimal(audio_tag["clip-begin"].split("=")[1][:-1]) + start_time
        seg_end = Decimal(audio_tag["clip-end"].split("=")[1][:-1]) + start_time
        audio.segments.append(Segment(identifier, seg_start, seg_end))
    return audio


def parse_command_line() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input-directory", nargs="?", required=True)
    parser.add_argument("-o", "--output-directory", nargs="?", required=True)
    return parser.parse_args()


def exit_with_error(message: str):
    """Print an error message and exit the program."""
    print(message)
    sys.exit(1)


def get_smils(ncc_path: str, encoding: str = "utf-8") -> list[Smil]:
    """Extract SMIL information from the NCC file."""
    with open(ncc_path, encoding=encoding) as f:
        ncc = BeautifulSoup(f, "xml")

    headings = ncc.find_all(["h1", "h2", "h3"])
    smil_list = []
    current_h1 = None
    current_h2 = None

    for heading in headings:
        level = int(heading.name[1])
        title = heading.a.text.strip()
        path = heading.a["href"].split("#")[0]

        if level == 1:
            if (
                sib := heading.find_next_sibling(["h1", "h2", "h3"])
            ) and sib.name != "h1":
                current_h1 = Smil(level, title, path, [])
                smil_list.append(current_h1)
            current_h2 = None
        elif level == 2:
            current_h2 = Smil(level, title, path, [])
            if current_h1:
                current_h1.children.append(current_h2)
        elif level == 3:
            smil = Smil(level, title, path, [])
            if current_h2:
                current_h2.children.append(smil)
    return smil_list


def make_safe_filename(filename: str) -> str:
    """Create a safe filename by removing or replacing disallowed characters."""
    disallowed_ascii = [chr(i) for i in range(0, 32)]
    disallowed_chars = '<>:"/\\|?*^{}'.format("".join(disallowed_ascii))
    translator = dict((ord(char), "_") for char in disallowed_chars)
    return filename.replace(": ", " - ").translate(translator).rstrip(". ")


if __name__ == "__main__":
    main()
