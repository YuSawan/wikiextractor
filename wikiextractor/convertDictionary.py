import argparse
import html
import json
import logging
import os
import unicodedata
from itertools import accumulate
from string import punctuation
from typing import Any, Iterator, TypedDict
from urllib.parse import unquote as urldecode

from bs4 import BeautifulSoup, NavigableString, Tag

from .WikiExtractor import decode_open

FORMAT = '%(levelname)s: %(message)s'
logging.basicConfig(format=FORMAT)

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class Entity(TypedDict):
    start: int
    end: int
    name: str
    title: str


def get_name_to_ids(input_file: str) -> dict[str, dict[str, str]]:
    input = decode_open(input_file, encoding='utf-8')
    dictionary = {}
    for line in input:
        data = json.loads(line)
        id, title, redirect = data['id'], data['title'], data['redirect']
        dictionary[title] = {'id': id, 'redirect': redirect}
    return dictionary


def get_offsets(soup: BeautifulSoup) -> Iterator[tuple[str, str, list[tuple[int, int, str, str]]]]:
    contents = soup.contents
    segments: list[str] = []
    spans: list[tuple[int, int, str, str]] = []
    begin = 0
    header = ''
    for i, content in enumerate(contents):
        if isinstance(content, Tag):
            if content.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                if header not in ["See also", "External Links", "References"]:
                    yield header, ''.join(segments), spans
                segments, spans = [], []
                header = content.text
                begin = 0
            if content.name == 'a':
                anchor = unicodedata.normalize('NFKC', content.text)
                try:
                    title = html.unescape(urldecode(content.get('href')))
                except TypeError:
                    for n, c in enumerate(contents):
                        print(n, c)
                    print(i, content)
                    raise TypeError
                if title:
                    spans.append((begin, begin + len(anchor), anchor, title))
                if i < len(contents) - 1 and contents[i+1].text and contents[i+1].text[0] not in punctuation:
                    segments.append(anchor+' ')
                    begin += len(anchor) + 1
                else:
                    segments.append(anchor)
                    begin += len(anchor)

        if isinstance(content, NavigableString):
            text = unicodedata.normalize('NFKC', content.lstrip())
            segments.append(text)
            begin += len(text)
    if segments:
        yield header, ''.join(segments), spans


def get_ids(title: str, pages2ids: dict[str, dict[str, str]]) -> str | None:
    if title not in pages2ids:
        if '#' in title:
            sharp = title.find('#') # if sharp > 0: link to the internal page (e.g. #pewter city) else # link to the section (e.g. Regional form#Hisuian forms),
            if sharp > 0 and title[:sharp].strip() in pages2ids:
                title = title[:sharp].strip()
            else:
                if title.startswith('wikipedia') and not title.startswith('Wikipedia') and not title.startswith('http') and not title.startswith('#'):
                    logger.warning(f"Title {title} not found in pages2ids.")
                return None
        else:
            title = title[0].upper() + title[1:] # if title is same charcter to the anchor, it is possibly not separeted by |. In this case, we assume that the title is the same as the anchor.
            if title not in pages2ids:
                if title.startswith('wikipedia') and not title.startswith('Wikipedia') and not title.startswith('http') and not title.startswith('#'):
                    logger.warning(f"Title {title} not found in pages2ids.")
                return None

    redirect = pages2ids[title]['redirect']
    if redirect:
        if redirect not in pages2ids:
            logger.warning(f"Redirect {redirect} not found in pages2ids for title {title}.")
            return None
        else:
            return pages2ids[redirect]['id']
    else:
        return pages2ids[title]['id']


def split_span(text: str, spans: list[tuple[int, int, str, str]]) -> tuple[list[str], list[list[Entity]]]:
    texts = text.split('\n')
    split_spans: list[list[Entity]] = [[] for _ in texts]
    cumsum_lens = list(accumulate([len(t)+1 for t in texts]))
    for b, e, a, n in spans:
        for i, cl in enumerate(cumsum_lens):
            if e < cl:
                prev_lens = cumsum_lens[i-1] if i > 0 else 0
                if a != texts[i][b - prev_lens: e - prev_lens]:
                    continue
                # assert a == texts[i][b - prev_lens: e - prev_lens]
                split_spans[i].append(Entity(start=b - prev_lens, end=e - prev_lens, name=a, title=n))
                break

    filtered_text, filtered_span = [], []
    for t, s in zip(texts, split_spans):
        if t:
            filtered_text.append(t)
            filtered_span.append(s)
    return filtered_text, filtered_span


def convert_for_entity_linking(input_file: str) -> Iterator[tuple[str, str, list[dict[str, Any]]]]:
    input = decode_open(input_file, encoding='utf-8')
    for line in input:
        examples: list[dict[str, Any]] = []
        data = json.loads(line)
        id, title = data['id'], html.unescape(data['title'])

        text = html.unescape(data['text'])
        soup = BeautifulSoup(text, 'html.parser')
        for template in soup.find_all(['ul', 'ol', 'infoxbox']):
            _ = template.extract()

        for header, text, spans in get_offsets(soup):
            if not text:
                continue
            header = 'Abstract' if not header else header
            d = []
            texts, split_spans = split_span(text, spans)
            for txt, ss in zip(texts, split_spans):
                d.append({"text": txt, "entities": ss})
            examples.append({header: d})

        yield id, title, examples


def main() -> None:
    parser = argparse.ArgumentParser(description="Split a history file into multiple files based on the number of lines.")
    parser.add_argument("--input_file", "-i", type=str, help="The input xml file to split.")
    parser.add_argument("--output_dir", "-o", type=str, default='output', help="The output xml file to split following to the timecut.")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    dictionary_output = open(os.path.join(args.output_dir, 'dictionary.json'), 'w')
    for id, title, examples in convert_for_entity_linking(args.input_file):
        if examples:
            dictionary_output.write(json.dumps({"id": id, "title": title, "text": examples}, ensure_ascii=False) + '\n')
    dictionary_output.close()

if __name__ == "__main__":
    main()
