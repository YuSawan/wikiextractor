import argparse
import logging
import re
from datetime import datetime
from typing import Any, Iterator

from .extract import acceptedNamespaces
from .WikiExtractor import decode_open, tagRE

FORMAT = '%(levelname)s: %(message)s'
logging.basicConfig(format=FORMAT)

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def convert_timestamp_to_date(timestamp: str) -> datetime:
    return datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%SZ')


def get_header_footer(input_file: str) -> tuple[str, str, str]:
    input = decode_open(input_file)

    # collect siteinfo
    lines: list[str] = []
    for line in input:
        assert isinstance(line, str), "Input must be a text file"
        line = line #.decode('utf-8')
        lines.append(line)
        m = tagRE.search(line)
        if not m:
            continue
        tag = m.group(2)
        # if tag == 'base':
        #     pass
        #     discover urlbase from the xml dump file
        #     /mediawiki/siteinfo/base
        #     base = m.group(3)
        #     urlbase = base[:base.rfind("/")]
        if tag == 'namespace':
            if re.search('key="10"', line):
                templateNamespace = m.group(3)
        elif tag == '/siteinfo':
            break

    input.close()

    header = ''.join(lines)
    footer = '</mediawiki>'
    return header, footer, templateNamespace


def collect_pages(input_file: str, templateNamespace: str) -> Iterator[tuple[str, str, str, str, list[Any]]]:
    """
    :param text: the text of a wikipedia file dump.
    """
    # we collect individual lines, since str.join() is significantly faster
    # than concatenation
    input = decode_open(input_file)

    page = []
    id = ''
    revid = ''
    namespace = ''
    timestamp = ''
    last_revid = ''
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
        elif tag == 'redirect':
            pass
        elif tag == 'revision':
            inText = True
            page = []
        elif tag == '/revision':
            inText = False
            colon = title.find(':')
            if (namespace == '0' or title[:colon] in acceptedNamespaces + [templateNamespace]) and last_revid != revid:
                yield id, revid, timestamp, title, page
                last_revid = revid
            revid = ''
            timestamp = ''
            page = []
            inText = False
        elif tag == '/page':
            id = ''
            namespace = ''
        else:
            page.append(line)
            if tag == 'id' and id and not revid: # <revision> <id></id> </revision>
                revid = m.group(3)
            elif tag == 'id' and id and revid: # <contributor> <id><id> </contribution>
                pass
            elif tag == 'timestamp': # <revision> <id></id> </revision>
                timestamp = m.group(3)
            elif tag == 'text':
                if m.lastindex == 4:  # open-close
                    inText = False
            elif tag == '/text':
                pass
            # elif inText:
            #     page.append(line)
    input.close()


def get_stable_period(curr_time: datetime, prev_time: datetime, timecut: datetime, lookback: datetime) -> float:
    """
    Decide if the timestamp is within the lookback period and before the timecut.
    """
    gap = curr_time - prev_time
    if prev_time < lookback:
        gap -= (lookback - prev_time)
    if curr_time > timecut:
        gap -= (curr_time - timecut)
    return gap.total_seconds()


def split_history(input_file: str, templateNamespace: str, timecut: str, min_days_stable_page_version: int, max_look_back_for_stable_page_version: int) -> Iterator[tuple[str, str, list[str]]]:
    prev_id, prev_title = '', ''
    prev_revision_date, prev_revision_page = None, None
    secure_revision_page = None
    max_time_lapse_between_revisions = 0.
    filtered_date = convert_timestamp_to_date(timecut)
    for id, _, timestamp, title, page in collect_pages(input_file, templateNamespace):
        if prev_id != id:
            if prev_id:
                if prev_revision_date is not None:
                    lapse_between_last_version_and_cut = (filtered_date - prev_revision_date).total_seconds()
                    if max_time_lapse_between_revisions > 0.0 and \
                        ((max_time_lapse_between_revisions <= lapse_between_last_version_and_cut) or (lapse_between_last_version_and_cut / 86400) >= min_days_stable_page_version):
                        secure_revision_page = prev_revision_page
                assert prev_id and prev_title
                if secure_revision_page:
                    yield prev_id, prev_title, secure_revision_page
                prev_revision_date, prev_revision_page = None, None
                secure_revision_page = None
                max_time_lapse_between_revisions = 0
            prev_id = id
            prev_title = title

        revision_date = convert_timestamp_to_date(timestamp)
        if (revision_date <= filtered_date or (prev_revision_date is not None and prev_revision_date <= filtered_date)) \
            and ((prev_revision_date is None) or (revision_date > prev_revision_date)):
            if prev_revision_date is None:
                # IF it is the first one, puts it anyway, no other choice
                prev_revision_date = revision_date
                prev_revision_page = page
                secure_revision_page = page
            else:
                curr_lapse_from_filter_date = (filtered_date - revision_date).days
                if curr_lapse_from_filter_date > max_look_back_for_stable_page_version:
                    if revision_date <= filtered_date:
                        secure_revision_page = page
                    else:
                        assert prev_revision_date <= filtered_date
                        secure_revision_page = prev_revision_page

                    prev_revision_page = page
                    prev_revision_date = revision_date
                else:
                    # here control well in order to not assign malicious content
                    curr_lapse = (revision_date - prev_revision_date).total_seconds()
                    assert curr_lapse >= 0
                    assert prev_revision_date <= filtered_date
                    if curr_lapse > max_time_lapse_between_revisions or \
                        (curr_lapse / 86400) >= min_days_stable_page_version:
                        secure_revision_page = prev_revision_page
                        max_time_lapse_between_revisions = max(curr_lapse, max_time_lapse_between_revisions)

                    prev_revision_date = revision_date
                    prev_revision_page = page

    if prev_revision_date is not None:
        lapse_between_last_version_and_cut = (filtered_date - prev_revision_date).total_seconds()
        if max_time_lapse_between_revisions > 0.0 and \
            ((max_time_lapse_between_revisions <= lapse_between_last_version_and_cut) or (lapse_between_last_version_and_cut / 86400) >= min_days_stable_page_version):
            secure_revision_page = prev_revision_page
        assert prev_id and prev_title
        if secure_revision_page:
            yield prev_id, prev_title, secure_revision_page


def convert_xml(input_file: str, output_file: str, time_cut: str, min_days_stable_page_version: int, max_look_back_for_stable_page_version: int) -> None:
    header, footer, templateNamespace = get_header_footer(input_file)
    output = open(output_file, 'w')
    output.write(header)

    for i, (id, title, page) in enumerate(split_history(input_file, templateNamespace, time_cut, min_days_stable_page_version, max_look_back_for_stable_page_version)):
        output.write('  <page>\n')
        output.write(f'    <title>{title}</title>\n')
        output.write('    <ns>0</ns>\n')
        output.write(f'    <id>{id}</id>\n')
        output.write('    <revision>\n')
        output.write(''.join(page))
        output.write('    </revision>\n')
        output.write('  </page>\n')
        if i % 1000 == 0:
            logging.info(f"Processed {i} pages...")
    output.write(footer)
    output.close()

    logging.info(f"Converted {i + 1} pages to XML format and saved to {output_file}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Split a history file into multiple files based on the number of lines.")
    parser.add_argument("--input_file", "-i", type=str, help="The input xml file to split.")
    parser.add_argument("--output_file", "-o", type=str, help="The output xml file to split following to the timecut.")
    parser.add_argument("--time_cut", "-t", type=str, default='2025-01-01T00:00:00Z', help="Cutoff date for processing pages.")
    parser.add_argument("--min_days_stable_page_version", "-m", type=int, default=10, help="Minimum days for a stable page version.")
    parser.add_argument("--max_look_back_for_stable_page_version", "-l", type=int, default=30, help="Maximum look back days for a stable page version.")
    args = parser.parse_args()

    convert_xml(args.input_file, args.output_file, args.time_cut, args.min_days_stable_page_version, args.max_look_back_for_stable_page_version)


if __name__ == "__main__":
    main()
