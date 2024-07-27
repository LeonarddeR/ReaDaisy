# daisy-extract
# Copyright (C) 2016 James Scholes
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
    """
    Represents a SMIL document in a DAISY book.

    The `Smil` class encapsulates information about a SMIL document,
    including its level in the document hierarchy, title, and file name.
    It may also have a list of child `Smil` objects representing nested SMIL documents.
    """

    level: int
    title: str
    file_name: str
    children: list[Self] | None = None


@dataclass
class Audio:
    """
    Represents an audio file with a start and end time.

    The `Audio` class encapsulates information about an audio file,
    including its identifier, file name, start time, and end time.
    This information is typically used in the context of a DAISY book,
    where multiple audio files are synchronized with a SMIL document.
    """

    identifier: str
    file_name: str
    start: Decimal
    end: Decimal


def main():
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


def copy_audio_file(input_directory, book_dir, current_file_name, new_filename):
    source_path = os.path.join(input_directory, current_file_name)
    destination_path = os.path.join(book_dir, new_filename)
    shutil.copy2(source_path, destination_path)


def process_books(
    smils: list[Smil],
    input_directory: str,
    output_directory: str,
    book_start_number: int,
):
    for index, book in enumerate(smils, start=book_start_number):
        book_dir = os.path.join(output_directory, f"{index:02d} - {book.title}")
        os.makedirs(book_dir, exist_ok=True)

        smil_path = os.path.join(input_directory, book.file_name)
        smil_content = parse_smil_document(smil_path)
        audio_files = get_audio_files(smil_content)
        book_start = get_start_time(smil_content)
        audio_file_name = audio_files[0].file_name

        new_file_name = f"00 - {book.title}{os.path.splitext(audio_file_name)[1]}"
        new_file_name = make_safe_filename(new_file_name)
        copy_audio_file(input_directory, book_dir, audio_file_name, new_file_name)

        total_chapters = len(book.children)
        chapter_padding = len(str(total_chapters))

        for chapter in book.children:
            smil_path = os.path.join(input_directory, chapter.file_name)
            smil_content = parse_smil_document(smil_path)
            rel_start = get_start_time(smil_content) - book_start
            chapter_audio_files = get_audio_files(
                smil_content, rel_start, f"{chapter}_"
            )

            total_subheadings = len(chapter.children)
            subheading_padding = len(str(total_subheadings))

            new_file_name = (
                f"{chapter.title.zfill(chapter_padding)} - "
                f"{str(0).zfill(subheading_padding)}{os.path.splitext(chapter_audio_files[0].file_name)[1]}"
            )
            new_file_name = make_safe_filename(new_file_name)
            copy_audio_file(
                input_directory,
                book_dir,
                chapter_audio_files[0].file_name,
                new_file_name,
            )

            audio_files += chapter_audio_files
            for subheading_index, subheading in enumerate(chapter.children, start=1):
                smil_path = os.path.join(input_directory, subheading.file_name)
                smil_content = parse_smil_document(smil_path)
                rel_start = get_start_time(smil_content) - book_start
                subheading_audio_files = get_audio_files(
                    smil_content, rel_start, f"{chapter}_{subheading_index}"
                )

                subheading_new_file_name = (
                    f"{chapter.title.zfill(chapter_padding)} - "
                    f"{str(subheading_index).zfill(subheading_padding)} - "
                    f"{subheading.title}{os.path.splitext(subheading_audio_files[0].file_name)[1]}"
                )
                subheading_new_file_name = make_safe_filename(subheading_new_file_name)
                copy_audio_file(
                    input_directory,
                    book_dir,
                    subheading_audio_files[0].file_name,
                    subheading_new_file_name,
                )

                audio_files += subheading_audio_files
        # Write audio_files to a CSV file for REAPER markers
        csv_filename = os.path.join(book_dir, f"{index:02d} - {book.title}_markers.csv")
        with open(csv_filename, "w", newline="") as csvfile:
            csv_writer = csv.writer(csvfile)
            csv_writer.writerow(["#", "Name", "Start", "End", "Length"])
            for i, audio in enumerate(audio_files, start=1):
                start = audio.start
                end = audio.end
                length = end - start
                csv_writer.writerow(
                    [
                        f"r{i}",
                        f"{i}{audio.identifier}",
                        start,
                        end,
                        length,
                        "",
                    ]
                )


def parse_smil_document(smil_path):
    with open(smil_path, encoding="utf-8") as f:
        return BeautifulSoup(f, "xml")


def get_start_time(smil_content) -> Decimal:
    meta_tag = smil_content.find("meta", attrs={"name": "ncc:totalElapsedTime"})

    if not meta_tag:
        raise RuntimeError("No meta tag found")
    time_str = meta_tag["content"]
    parts = time_str.split(":")

    total_seconds = sum(
        Decimal(part) * (60**i) for i, part in enumerate(reversed(parts))
    )
    return total_seconds


def get_audio_files(
    smil_content, start_time: Decimal = 0, id_prefix: str = ""
) -> list[Audio]:
    audio_files = []
    for audio_tag in smil_content.find_all("audio"):
        file_name = audio_tag["src"]
        start = Decimal(audio_tag["clip-begin"].split("=")[1][:-1]) + start_time
        end = Decimal(audio_tag["clip-end"].split("=")[1][:-1]) + start_time
        identifier = f"{id_prefix}{int(audio_tag["id"].split("_")[-1], base=16)}"
        audio_files.append(Audio(identifier, file_name, start, end))
    # Check if all audio files have the same filename
    if not all(audio.file_name == file_name for audio in audio_files):
        raise ValueError(f"Not all audio files have the same filename: {file_name}")
    return audio_files


def parse_command_line():
    """
    Parses the command line arguments for the application.

    This function uses the `argparse` module to define and parse the
    command line arguments for the application.
    It expects two required arguments:

    - `--input-directory`: The directory containing the input files.
    - `--output-directory`: The directory to write the output files to.

    The function returns the parsed arguments as an `argparse.Namespace` object.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input-directory", nargs="?", required=True)
    parser.add_argument("-o", "--output-directory", nargs="?", required=True)

    args = parser.parse_args()
    return args


def exit_with_error(message):
    print(message)
    sys.exit(1)


def get_smils(ncc_path, encoding="utf-8") -> list[Smil]:
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


def make_safe_filename(filename):
    # strip out any disallowed chars and replace with underscores
    disallowed_ascii = [chr(i) for i in range(0, 32)]
    disallowed_chars = '<>:"/\\|?*^{}'.format("".join(disallowed_ascii))
    translator = dict((ord(char), "_") for char in disallowed_chars)
    safe_filename = filename.replace(": ", " - ").translate(translator).rstrip(". ")
    return safe_filename


if __name__ == "__main__":
    main()
