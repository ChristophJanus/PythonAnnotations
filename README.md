# PythonAnnotations
This was the code used to analyze Python type annotations in my bachelor thesis at the proglang chair at the University of Freiburg.
https://proglang.informatik.uni-freiburg.de/

The thesis has three analysis parts:
1. Quantitative analysis of type annotations in the top 1000 Python repositories on GitHub for ten years (2013 - 2022).
2. Qualitative analysis of type annotations in 50 random repositories.
3. mypy analysis: Check repositories with no mypy errors for type errors with random inputs for functions with full annotations

## Documentation

### Requirements

A linux environment is assumed for file path building and used for bash scripts. Python packages used are:
clipboard
mypy
mysql-connector-python

### Data retrieval

scripts/data_retrieval/get_repository_data.sh\
This script is used to retrieve the data from the GitHub API. It is used to get the top-rated repositories for each year. Since GitHubs's response is inconsistent it is done five times per year and later combined.

scripts/data_retrieval/merge_repository_data.py\
This script takes the five files for each year and combines them, sorts them by most stars and limits top 1000 repositories to create the final list of repositories to clone.

scripts/data_retrieval/clone_repositories.sh\
This script clones the repositories from the list created by merge_repository_data.py.

### Database creation

scripts/sql/read_repository_json.py\
This file reads the json files created by merge_repository_data.py to create the first database table "repository" with information about every repository (id, name, owner, stars, clone_url).

scripts/sql/db_fill_repos.py\
This file provides the connectivity to the mysql server. It is used to fill the repository with the above information. It also provides the functions to later at the analyzed information to the databse.

### Analysis

scipts/analyzer/analyzer.py\
This is the main file to provide data for the quantitative analysis. It is used to analyze the repositories with an ast-based algorithm. It also enters the found information into the database.

scripts/analyzer/slim_analyzer.py\
This module is used for the mypy analysis. It uses a slimmed down version of the ast-based algorithm to find the type annotations for speed reasons.
