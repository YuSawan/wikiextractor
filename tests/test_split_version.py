import json
import os


def test_splitRevision() -> None:
    assert os.path.exists('current/AA/wiki_00')
    assert os.path.exists('2025/AA/wiki_00')

    current_file = open(os.path.join('current/AA', 'wiki_00'))
    test_file = open(os.path.join('2025/AA/', 'wiki_00'))
    assert len(current_file.readlines()) == len(test_file.readlines())

    current_file = open(os.path.join('current/AA', 'wiki_00'))
    test_file = open(os.path.join('2025/AA/', 'wiki_00'))
    for c_line, t_line in zip(current_file, test_file):
        c_data = json.loads(c_line)
        t_data = json.loads(t_line)
        assert c_data['id'] == t_data['id']
        assert c_data['revid'] == t_data['revid']
        assert c_data['url'] == t_data['url']
        assert c_data['title'] == t_data['title']
        for cl, tl in zip(c_data['text'].split('\n'), t_data['text'].split('\n')):
            assert cl == tl
