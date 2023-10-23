"""Merge GitHub REST API results.

GitHub's API results are inconsistent. This module merges multiple requests.
It checks for duplicates and sorts the results by descending stars limiting
the number of repositories to 1000.

"""


import json
from typing import Union


def generate_file_names(year: int,
                        number_iterations: int,
                        file_type: str) -> tuple[str, list[str]]:
    files = list()
    output = "github_data_{}.{}".format(year, file_type)
    for num in range(number_iterations):
        files.append(
            "github_data_{}_{}.{}".format(year, num, file_type)
        )
    return output, files


def eq_repos(repo1: dict, repo2: dict):
    check = repo1['name'] == repo2['name'] and \
        repo1['created_at'] == repo2['created_at']
    if not check and repo1['name'] == repo2['name']:
        print("ERROR: Only names are equal:", repo1['name'])
    if not check and repo1['created_at'] == repo2['created_at']:
        print("ERROR: Only dates are equal:", repo1['created_at'])
    return check


def get_repo_most_stars(j0, j1, j2, j3, j4) -> dict:
    repo_with_most_stars = j0
    if j1['stars'] > repo_with_most_stars['stars']:
        repo_with_most_stars = j1
    if j2['stars'] > repo_with_most_stars['stars']:
        repo_with_most_stars = j2
    if j3['stars'] > repo_with_most_stars['stars']:
        repo_with_most_stars = j3
    if j4['stars'] > repo_with_most_stars['stars']:
        repo_with_most_stars = j4
    return repo_with_most_stars


def remove_repo_from_top(repository, repo_list, num: int = 10):
    for i in range(num):
        try:
            if eq_repos(repository, repo_list[i]):
                repo_list.pop(i)
        except IndexError:
            break
    return repo_list


def merge_results(file_out: str, files_in: list[str]):
    assert len(files_in) == 5
    with open(files_in[0], 'r') as f1, \
            open(files_in[1], 'r') as f2, \
            open(files_in[2], 'r') as f3, \
            open(files_in[3], 'r') as f4, \
            open(files_in[4], 'r') as f5, \
            open(file_out, 'w', encoding='utf-8') as fo:
        d1 = json.load(f1)
        d2 = json.load(f2)
        d3 = json.load(f3)
        d4 = json.load(f4)
        d5 = json.load(f5)
        data = list()
        len_json = 1000
        for i in range(len_json):
            if i == 177 or i == 234 or i == 293:
                last = data[-1]
                pass
            repo = get_repo_most_stars(d1[0], d2[0], d3[0], d4[0], d5[0])
            d1 = remove_repo_from_top(repo, d1)
            d2 = remove_repo_from_top(repo, d2)
            d3 = remove_repo_from_top(repo, d3)
            d4 = remove_repo_from_top(repo, d4)
            d5 = remove_repo_from_top(repo, d5)
            data.append(repo)
        json.dump(data, fo, ensure_ascii=False, indent=4)


def is_in_repo(repository, repo_list):
    for repo in repo_list:
        if eq_repos(repo, repository):
            return True
    return False


def validate_json(file_name: str, verbose: Union[bool, str] = False):
    with open(file_name) as f:
        if verbose:
            print("Checking file:", file_name)
        data = json.load(f)
        valid_data = list()
        duplicates = 0
        order_errors = 0
        last_star = 1000000
        # Check duplicates
        for i, repo in enumerate(data):
            if is_in_repo(repo, valid_data):
                duplicates += 1
                if verbose == "full":
                    print("Error: Duplicate #{}: {}".format(i, repo['name']))
            else:
                valid_data.append(repo)
        # Checking descending star order
        for i, repo in enumerate(data):
            current_star = repo['stars']
            if not current_star <= last_star:
                order_errors += 1
                if verbose:
                    print("Error: Order #{}: {}".format(i, repo['name']))
            last_star = current_star
        if verbose:
            print("Found {} dupes and {} order_errors with {} entries".format(
                duplicates, order_errors, len(valid_data)))


def correct_json(file_name: str, verbose: Union[bool, str] = False):
    """Making sure json are in "star-descending" order."""
    if verbose:
        print("Correcting:", file_name)
    data = list()
    valid_data = list()
    # Read data
    with open(file_name, 'r') as fr:
        data = json.load(fr)
    # Ensure star-descending order
    data.sort(key=lambda x: x['stars'], reverse=True)
    for repo in data:
        if not is_in_repo(repo, valid_data):
            valid_data.append(repo)
    if verbose:
        if len(data) != len(valid_data):
            print("New length:", len(valid_data))
    # Write potentially new data to same file
    with open(file_name, 'w', encoding='utf-8') as fw:
        json.dump(valid_data, fw, ensure_ascii=False, indent=4)


if __name__ == '__main__':
    year_begin, year_end = 2013, 2022
    for year in range(year_begin, year_end + 1):
        output_file, input_files = generate_file_names(year, 5, "json")
        for file in input_files:
            correct_json(file)
            validate_json(file)
        merge_results(output_file, input_files)
        validate_json(output_file, verbose="full")
