"""A module to read GitHub repositories.
Repository information given through GitHub's REST API can be read with
this module. BUT storage of that information in a specific json format is
assumed.

Author: Christoph Janus
    <janusc@cs.uni-freiburg.de>

"""

import json
from os import path, getcwd
from typing import Optional


class Repo:
    """A Class for a GitHub repository used in my thesis.

    Attributes:
        user (str)      : Creator of the repository.
        name (str)      : Name of the repository.
        created_at (str): Creation datetime of the repository.
        clone_url (str) : Used to clone the repository.
        stars (int)     : Number of stars the repository got.
                          (At time of data collection)
    """
    def __init__(self,
                 name: str = "/",
                 url: str = "",
                 stars: int = 0,
                 creation_datetime: str = ""):
        self.user, self.name = name.split("/")
        self.created_at = self.format_datetime(creation_datetime)
        self.clone_url = url
        self.stars = stars

    @staticmethod
    def format_datetime(dt: str) -> str:
        """Format the datetime string to the right format.

        From GitHub's format to mysql format.
        "YYYY-MM-DDTHH:MM:SSZ" -> ""YYYY-MM-DD HH:MM:SS"
        Replace 'T' with ' ' and strip 'Z'

        Args:
            dt (str): Datetime in GitHub's format.

        Returns:
            A str representing the same datetime in mysql readable format.

        Examples:
            >>> Repo().format_datetime("2013-10-28T13:19:39Z")
            '2013-10-28 13:19:39'
            >>> Repo().format_datetime("2022-10-17T02:58:36Z")
            '2022-10-17 02:58:36'

        """
        return dt.replace('T', ' ')[:-1]

    def get_year(self) -> int:
        """Get the year of creation.

        Returns:
            An int representing the year of creation.

        Examples:
            >>> Repo(name="test/test", url="test", stars=0, \
                creation_datetime="2022-10-17T02:58:36Z").get_year()
            2022

        """
        return int(self.created_at[:4])


class RepoHandler:
    """A module to store repositories.
    It provides functions to read from the json-files."""
    def __init__(self):
        self.repos: list[Repo] = list()

    def get_repo(self, repo_name: str) -> Optional[Repo]:
        """Get a repository by name.

        Args:
            repo_name (str): Name of the repository.

        Returns:
            A Repo object if the repository is in memory, else None.
        """
        for repo in self.repos:
            if repo.name == repo_name:
                return repo
        return None

    def read_from_file(self, file_name: str):
        """Read repositories from a json file.
        Add them to memory.

        Args:
            file_name (str): Name of the file to read from.
        """
        # Read repos from json file
        with open(file_name) as f:
            data = json.load(f)
        # Add each repo to memory
        for repo in data:
            self.repos.append(
                Repo(
                    name=repo['name'],
                    url=repo['url'],
                    stars=repo['stars'],
                    creation_datetime=repo['created_at']
                )
            )

    def read_repo_files(self):
        """Read all repository files from 2013 to 2022."""
        if path.basename(getcwd()) != "data":
            parent_folder = path.dirname(getcwd())
        else:
            parent_folder = getcwd()
        file_names = [path.join(parent_folder, f"github_data_{year}.json")
                      for year in range(2022, 2012, -1)]
        for file_name in file_names:
            self.read_from_file(file_name)

    def get_longest_repo_name(self) -> tuple[int, int, str]:
        """Get the longest repository name.

        Returns:
            The number of characters of the longest name and the name itself.

        Examples:
            >>> repo_test = RepoHandler()
            >>> repo_test.read_from_file("test.json")
            >>> repo_test.get_longest_repo_name()
            (2013, 12, 'cookiecutter')

        """
        longest_name, year = "", int()
        for repo in self.repos:
            if len(repo.name) > len(longest_name):
                longest_name, year = repo.name, repo.get_year()
        return year, len(longest_name), longest_name

    def get_longest_clone_url(self) -> tuple[int, int, str]:
        """Get the longest clone url.

        Returns:
            The number of characters of the longest url and the url itself.

        Examples:
            >>> repo_test = RepoHandler()
            >>> repo_test.read_from_file("test.json")
            >>> repo_test.get_longest_clone_url()
            (2013, 58, 'https://github.com/facebookresearch/maskrcnn-benchmark.git')

        """
        longest_url, year = "", int()
        for repo in self.repos:
            if len(repo.clone_url) > len(longest_url):
                longest_url, year = repo.clone_url, repo.get_year()
        return year, len(longest_url), longest_url


if __name__ == '__main__':
    repos = RepoHandler()
    repos.read_repo_files()
    print(repos.get_longest_clone_url())
