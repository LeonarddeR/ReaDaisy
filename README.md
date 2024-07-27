# ReaDaisy

ReaDaisy is a Python tool for processing DAISY (Digital Accessible Information System) books.
It extracts audio content and metadata from DAISY books, reorganizes them into a more accessible structure, and creates Reaper project files for easy audio editing.
Note that the current project was inspired by [daisy-extract](https://github.com/jscholes/daisy-extract).
It is also mainly used to reaperize Bible Daisy books.
Therefore all headings at level 1 are treated as separate books and therefore extracted into separate folders and projects.

## Features

- Extracts audio files and metadata from DAISY 2.02 books
- Organizes content into a hierarchical structure (books, chapters, subheadings)
- Renames audio files based on their content and position in the book
- Creates Reaper project files (.RPP) with proper track layout and markers
- Supports batch processing of multiple books

## Requirements

- Python 3.11 or higher
- beautifulsoup4 with lxml
- reathon

## Installation

1. Clone the repository:
1. Install the required packages:

## Usage

Run the script with the following command:
`python readaisy.py -i <input_directory> -o <output_directory>`

Where:

- `<input_directory>` is the path to the directory containing DAISY books
- `<output_directory>` is the path where you want the processed files to be saved

## Output

For each processed book, ReaDaisy will create:

- A directory structure organizing the book's content
- Renamed and numbered audio files
- A Reaper project file (.RPP) for audio editing

## License

This project is licensed under the GNU General Public License v3.0. See the LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
