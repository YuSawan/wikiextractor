import argparse
import json
import logging
import re
from typing import Iterator
import html

from .extract import acceptedNamespaces
from .WikiExtractor import decode_open, redirect_patterns, tagRE

FORMAT = '%(levelname)s: %(message)s'
logging.basicConfig(format=FORMAT)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

move_patterns = ['(^|\s)moved (\[\[.*?\]\]) to (\[\[.*?\]\])', '(^|\s)moved page (\[\[.*?\]\]) to (\[\[.*?\]\])']



def collect_revisions(input_file: str) -> Iterator[tuple[str, str, str, str, str, list[str]]]:
    """
    :param text: the text of a wikipedia file dump.
    """
    # we collect individual lines, since str.join() is significantly faster
    # than concatenation
    input = decode_open(input_file)

    id = ''
    revid = ''
    namespace = ''
    timestamp = ''
    last_revid = ''
    comment = ''
    page = []
    inText = False
    for line in input:
        assert isinstance(line, str), "Input must be a text file"
        if '<' not in line:     # faster than doing re.search()
            if inText:
                page.append(line)
            continue
        m = tagRE.search(line)
        if not m:
            continue
        tag = m.group(2)
        if tag == 'page':
            pass
        elif tag == 'title':
            title = m.group(3)
        elif tag == 'ns':
            namespace = m.group(3)
        elif tag == 'id' and not id:
            id = m.group(3)
        elif tag == 'id' and id and not revid: # <revision> <id></id> </revision>
            revid = m.group(3)
        elif tag == 'redirect':
            pass
        elif tag == 'timestamp':
            timestamp = m.group(3)
        elif tag == 'comment':
            comment = m.group(3)
        elif tag == 'revision':
            pass
        elif tag == '/revision':
            colon = title.find(':')
            if (namespace == '0' or title[:colon] in acceptedNamespaces) and last_revid != revid:
                yield id, revid, timestamp, title, comment, page
                last_revid = revid
            revid = ''
            timestamp = ''
            comment = ''
            page = []
        elif tag == '/page':
            id = ''
            namespace = ''
        else:
            if tag == 'text':
                inText = True
                line = line[m.start(3):m.end(3)]
                page.append(line)
                if m.lastindex == 4:  # open-close
                    inText = False
            elif tag == '/text':
                if m.group(1):
                    page.append(m.group(1))
                inText = False
            elif inText:
                page.append(line)
    input.close()


def collect_comments(input_file: str) -> Iterator[tuple[str, str, list[str], list[str], list[bool]]]:
    prev_id = ''
    prev_title = ''
    prev_timestamps: list[str] = []
    prev_comments: list[str] = []
    prev_redirects: list[bool] = []
    for id, _, timestamp, title, comment, page in collect_revisions(input_file):
        if prev_id != id:
            if prev_id: # new page id
                yield prev_id, prev_title, prev_timestamps, prev_comments, prev_redirects
            prev_id, prev_title, prev_timestamps, prev_comments, prev_redirects = id, title, [], [], []
        find_redirect = False
        for redirect_pattern in redirect_patterns:
            result_pattern = redirect_pattern.search(''.join(page))
            if result_pattern:
                find_redirect = True
                break
        prev_redirects.append(find_redirect)
        prev_timestamps.append(timestamp)
        prev_comments.append(comment)

    if prev_id and prev_title is not None:
        yield prev_id, prev_title, prev_timestamps, prev_comments, prev_redirects


def get_titlechange_history(input_file: str, output_file: str) -> None:
    output = open(output_file, 'w')
    for i, (id, title, timestamps, comments, redirects) in enumerate(collect_comments(input_file)):
        assert len(timestamps) == len(comments)
        history = []
        for t, c, r in zip(timestamps, comments, redirects):
            old_page_title, new_page_title = None, None
            for curr_move_pattern in move_patterns:
                result_pattern = re.search(curr_move_pattern, c)
                if result_pattern:
                    old_page_title = result_pattern.group(2)[2:-2].strip()
                    new_page_title = result_pattern.group(3)[2:-2].strip()
                    if not (']]' in old_page_title or ']]' in new_page_title):
                        break  # once a pattern is found, no need to look for other patterns
                    else:
                        old_page_title = None
                        new_page_title = None
            if old_page_title and new_page_title:
                if not r:
                    history.append({"timestamp": t, "old_page_title": html.unescape(old_page_title), "new_page_title": html.unescape(new_page_title), "redirect": r})
        output.write(json.dumps({"id": id, "title": html.unescape(title), "history": history}, ensure_ascii=False) + '\n')
        if i % 1000 == 0:
            logging.info(f"Processed {i} pages...")
    output.close()

    logging.info(f"Converted {i + 1} pages to XML format and saved to {output_file}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Split a history file into multiple files based on the number of lines.")
    parser.add_argument("--input_file", "-i", type=str, help="The input xml file to split.")
    parser.add_argument("--output_file", "-o", default='page_history.jsonl', type=str, help="The output xml file to split following to the timecut.")
    args = parser.parse_args()

    get_titlechange_history(args.input_file, args.output_file)


if __name__ == "__main__":
    main()
