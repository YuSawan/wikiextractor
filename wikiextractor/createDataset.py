import argparse
import json
import logging
from typing import Any, Iterator

from .splitRevision import convert_timestamp_to_date
from .WikiExtractor import decode_open

FORMAT = '%(levelname)s: %(message)s'
logging.basicConfig(format=FORMAT)

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def read_history(history_file: str) -> dict[str, Any]:
    input = decode_open(history_file)
    history = {}
    for line in input:
        assert isinstance(line, str)
        data = json.loads(line)
        history[data["id"]] = {"title": data["title"], "history": data["history"]}
    input.close()
    return history


def search_history(timestamp: str, history_data: dict[str, Any]) -> str:
    title = history_data['title']
    if not history_data['history']:
        return title

    current_time = convert_timestamp_to_date(timestamp)
    for history in history_data['history'][::-1]:
        ts = convert_timestamp_to_date(history['timestamp'])
        if current_time >= ts:
            return title
        old, new = history['old_page_title'], history['new_page_title']
        assert new == title
        title = old
    return title


def read_titles2redirects(pages2redirects_file: str, history: dict[str, Any]) -> dict[str, str]:
    input = decode_open(pages2redirects_file)
    titles2redirects = {}
    for line in input:
        assert isinstance(line, str)
        data = json.loads(line)
        timestamp = data['timestamp']
        history_data = history[data['id']]
        assert data['title'] == history_data['title']
        title = search_history(timestamp, history_data)
        titles2redirects[title] = data['redirect']
    input.close()
    return titles2redirects


def read_ids2pages(dictionary_file: str, history: dict[str, Any]) -> dict[str, dict[str, str]]:
    input = decode_open(dictionary_file)
    ids2pages = {}
    for line in input:
        assert isinstance(line, str)
        data = json.loads(line)
        timestamp = data['timestamp']
        history_data = history[data['id']]
        assert data['title'] == history_data['title']
        title = search_history(timestamp, history_data)
        ids2pages[data['id']] = {"title": title, "timestamp": timestamp}
    input.close()
    return ids2pages


def check_title_in(title: str, titles2ids: dict[str, str]) -> str | None:
    if title not in titles2ids:
        if '#' in title:
            sharp = title.find('#')
            if sharp > 0 and title[:sharp].strip() in titles2ids:
                title = title[:sharp].strip()
            else:
                return None
        else:
            title = title[0].upper() + title[1:] # if title is same charcter to the anchor, it is possibly not separeted by |. In this case, we assume that the title is the same as the anchor.
            if title not in titles2ids:
                return None
    return title


def get_title(title: str, titles2redirects: dict[str, str]) -> str | None:
    check_title = check_title_in(title, titles2redirects)
    if not check_title:
        # if not title.lower().startswith('wikipedia') and not title.lower().startswith('http') and not title.startswith('#') and not title.lower().startswith('w:c'):
        #     logger.warning(f"Title {title} not found in pages2ids.")
        return None

    title = check_title
    while True:
        redirect = titles2redirects[title]
        if redirect is None:
            break

        title = redirect.replace('_', ' ')
        check_title = check_title_in(title, titles2redirects)
        if not check_title:
            return None
        title = check_title

    return title


def get_id(title: str | None, titles2ids: dict[str, str]) -> str | None:
    if not title:
        return None
    check_title = check_title_in(title, titles2ids)
    if check_title is None:
        if not title.lower().startswith('wikipedia') and not title.lower().startswith('http') and not title.startswith('#') and not title.lower().startswith('w:c'):
            logger.warning(f"Title {title} not found in title2ids.")
        return None
    title = check_title
    return titles2ids[title]


def filter_paraphs(paraphs: list[dict[str, Any]], titles2ids: dict[str, str], titles2redirects: dict[str, str]) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    for p in paraphs:
        if not p["entities"]:
            continue
        entities = []
        for e in p["entities"]:
            title = get_title(e['title'], titles2redirects)
            idx = get_id(title, titles2ids)
            if idx:
                entities.append({"start": e["start"], "end": e["end"], "name": e["name"], "label": [idx]})
        if entities:
            yield p["text"], entities


def convert_to_dataset(dictionary_file: str, ids2pages: dict[str, dict[str, str]], titles2redirects: dict[str, str]) -> dict[str, Any]:
    input = decode_open(dictionary_file)
    titles2ids = {v["title"]: k for k, v in ids2pages.items()}

    dataset: dict[str, dict[str, Any]] = {}
    for line in input:
        assert isinstance(line, str)
        data = json.loads(line)
        idx = data['id']
        title = ids2pages[idx]['title']
        abst_data = list(data['text'][0].values())[0]
        description = ' '.join([t['text'] for t in abst_data])

        examples: list[dict[str, Any]] = []
        if len(data['text']) > 1:
            for k in data['text'][1:]:
                for paraphs in k.values():
                    for text, entities in filter_paraphs(paraphs, titles2ids, titles2redirects):
                        examples.append({"id": len(examples), "text": text, "entities": entities})
        dataset[idx] = {"title": title, "description": description, "examples": examples}
    input.close()
    return dataset


def write_jsonl(dataset: dict[str, dict[str, Any]], output_file: str) -> None:
    with open(output_file, 'w', encoding='utf-8') as output:
        for idx, data in dataset.items():
            output.write(json.dumps({
                "id": idx,
                "title": data["title"],
                "description": data["description"],
                "examples": data["examples"]
            }, ensure_ascii=False) + '\n')


def convert_dictionary_to_dataset(input_file: str, history_file: str, page2redirect_file: str) -> dict[str, Any]:
    history = read_history(history_file)
    titles2redirects = read_titles2redirects(page2redirect_file, history)
    ids2pages = read_ids2pages(input_file, history)
    dataset = convert_to_dataset(input_file, ids2pages, titles2redirects)
    return dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert Dictionary to a Dataset while changing titles")
    parser.add_argument('--input_file', '-i', type=str)
    parser.add_argument('--output_file', '-o', type=str)
    parser.add_argument('--history_file', '-p', type=str)
    parser.add_argument('--page2redirect_file', '-r', type=str)
    args = parser.parse_args()

    dataset = convert_dictionary_to_dataset(args.input_file, args.history_file, args.page2redirect_file)
    write_jsonl(dataset, args.output_file)

if __name__ == "__main__":
    main()
