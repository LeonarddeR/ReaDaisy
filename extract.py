# daisy-extract
# Copyright (C) 2016-2014 James Scholes, Leonard de Ruijter
# This program is free software, licensed under the terms of the
# GNU General Public License (version 3 or later).
# See the file LICENSE for more details.

import argparse
import csv
import os
import shutil
import sys
from dataclasses import dataclass
from decimal import Decimal
from glob import glob
from typing import Self

from bs4 import BeautifulSoup

NCC_FILENAME = "NCC.HTML"


@dataclass
class Smil:
    """Represents a SMIL document in a DAISY book."""

    level: int
    title: str
    file_name: str
    children: list[Self] | None = None


@dataclass
class Audio:
    """Represents an audio file with a start and end time."""

    identifier: str
    file_name: str
    start: Decimal
    end: Decimal


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
        process_books(smils, ncc_dir, output_directory, book_start_number)
        book_start_number += len(smils)


def copy_audio_file(
    input_directory: str, book_dir: str, current_file_name: str, new_filename: str
):
    """Copy audio file from input directory to book directory."""
    source_path = os.path.join(input_directory, current_file_name)
    destination_path = os.path.join(book_dir, new_filename)
    shutil.copy2(source_path, destination_path)


def process_books(
    smils: list[Smil],
    input_directory: str,
    output_directory: str,
    book_start_number: int,
):
    """Process each book in the DAISY structure."""
    for index, book in enumerate(smils, start=book_start_number):
        book_dir = os.path.join(output_directory, f"{index:02d} - {book.title}")
        os.makedirs(book_dir, exist_ok=True)

        smil_path = os.path.join(input_directory, book.file_name)
        smil_content = parse_smil_document(smil_path)
        audio_files = get_audio_files(smil_content)
        book_start = get_start_time(smil_content)
        audio_file_name = audio_files[0].file_name

        new_file_name = make_safe_filename(
            f"00 - {book.title}{os.path.splitext(audio_file_name)[1]}"
        )
        copy_audio_file(input_directory, book_dir, audio_file_name, new_file_name)

        total_chapters = len(book.children)
        chapter_padding = len(str(total_chapters))

        for chapter in book.children:
            audio_files += process_chapter(
                chapter, input_directory, book_dir, book_start, chapter_padding
            )

        create_markers_csv(book_dir, index, book.title, audio_files)


def create_markers_csv(book_dir: str, index: int, title: str, audio_files: list[Audio]):
    """Create a CSV file with markers for REAPER."""
    csv_filename = os.path.join(book_dir, f"{index:02d} - {title}_markers.csv")
    with open(csv_filename, "w", newline="") as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerow(["#", "Name", "Start", "End", "Length"])
        for i, audio in enumerate(audio_files, start=1):
            start, end = audio.start, audio.end
            csv_writer.writerow(
                [
                    f"r{i}",
                    f"{i}{audio.identifier}",
                    start,
                    end,
                    end - start,
                    "",
                ]
            )


def process_chapter(
    chapter: Smil,
    input_directory: str,
    book_dir: str,
    book_start: Decimal,
    chapter_padding: int,
) -> list[Audio]:
    """Process a chapter within a book."""
    smil_path = os.path.join(input_directory, chapter.file_name)
    smil_content = parse_smil_document(smil_path)
    rel_start = get_start_time(smil_content) - book_start
    chapter_audio_files = get_audio_files(smil_content, rel_start, f"{chapter}_")

    total_subheadings = len(chapter.children)
    subheading_padding = len(str(total_subheadings))

    new_file_name = make_safe_filename(
        f"{chapter.title.zfill(chapter_padding)} - "
        f"{str(0).zfill(subheading_padding)}{os.path.splitext(chapter_audio_files[0].file_name)[1]}"
    )
    copy_audio_file(
        input_directory, book_dir, chapter_audio_files[0].file_name, new_file_name
    )

    for subheading_index, subheading in enumerate(chapter.children, start=1):
        chapter_audio_files += process_subheading(
            subheading,
            input_directory,
            book_dir,
            book_start,
            chapter,
            subheading_index,
            chapter_padding,
            subheading_padding,
        )

    return chapter_audio_files


def process_subheading(
    subheading: Smil,
    input_directory: str,
    book_dir: str,
    book_start: Decimal,
    chapter: Smil,
    subheading_index: int,
    chapter_padding: int,
    subheading_padding: int,
) -> list[Audio]:
    """Process a subheading within a chapter."""
    smil_path = os.path.join(input_directory, subheading.file_name)
    smil_content = parse_smil_document(smil_path)
    rel_start = get_start_time(smil_content) - book_start
    subheading_audio_files = get_audio_files(
        smil_content, rel_start, f"{chapter}_{subheading_index}"
    )

    subheading_new_file_name = make_safe_filename(
        f"{chapter.title.zfill(chapter_padding)} - "
        f"{str(subheading_index).zfill(subheading_padding)} - "
        f"{subheading.title}{os.path.splitext(subheading_audio_files[0].file_name)[1]}"
    )
    copy_audio_file(
        input_directory,
        book_dir,
        subheading_audio_files[0].file_name,
        subheading_new_file_name,
    )

    return subheading_audio_files


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


def get_audio_files(
    smil_content: BeautifulSoup, start_time: Decimal = 0, id_prefix: str = ""
) -> list[Audio]:
    """Extract audio file information from a SMIL document."""
    audio_files = []
    for audio_tag in smil_content.find_all("audio"):
        file_name = audio_tag["src"]
        start = Decimal(audio_tag["clip-begin"].split("=")[1][:-1]) + start_time
        end = Decimal(audio_tag["clip-end"].split("=")[1][:-1]) + start_time
        identifier = f"{id_prefix}{int(audio_tag["id"].split("_")[-1], base=16)}"
        audio_files.append(Audio(identifier, file_name, start, end))

    if not all(audio.file_name == file_name for audio in audio_files):
        raise ValueError(f"Not all audio files have the same filename: {file_name}")
    return audio_files


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
