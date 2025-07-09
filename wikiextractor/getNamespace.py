import argparse
import json

from wikiextractor.splitRevision import collect_pages, get_header_footer


def get_namespace(input_file: str) -> list[str]:
    namespaces = set()
    _, _, templateNamespace = get_header_footer(input_file)
    for _, _, _, title, _ in collect_pages(input_file, templateNamespace):
        colon = title.find(':')
        if colon != -1 and title[:colon] not in templateNamespace:
            namespaces.add(title[:colon])
    return sorted(namespaces)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract namespaces from a Wikia dump.")
    parser.add_argument('--input_file', '-i', type=str, help='Input file containing the Wikia dump')
    parser.add_argument('--output_file', '-o', type=str, help='Input file containing the Wikia dump')
    args = parser.parse_args()

    with open(args.output_file, 'w') as f:
        json.dump(get_namespace(args.input_file), f, ensure_ascii=False)


if __name__ == '__main__':
    main()
