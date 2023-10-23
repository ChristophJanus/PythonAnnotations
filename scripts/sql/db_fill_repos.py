"""Fill the my_sql database with information about repositories.
Use information read by read_repository_json.py for the repository table.

Table module, func_var and annotation are filled by analyzer.py calling upon
functions in this module.
Since calls to the database are slow. Information from analyzer.py is stored
in json files which then will be committed at once.
"""
import mysql.connector
import json
import time
from typing import Literal
# Own imports
import read_repository_json


class DBHelper:
    def __init__(self):
        self.db = self.connect_to_db()
        self.my_cursor: mysql.connector.cursor = self.db.cursor()
        self.module_commits = list()
        self.func_var_commits = list()
        self.annotation_commits = list()
        (self.repo_insert_query, self.module_insert_query,
         self.func_var_insert_query, self.annotation_insert_query) = \
            self.get_insert_queries()
        self.start_time = time.time()

    @staticmethod
    def connect_to_db() -> mysql.connector.MySQLConnection:
        db = mysql.connector.connect(
            host="localhost",
            user="root",
            password="...",
            database="thesis"
        )
        return db

    def clear_table(self, table_name: str):
        """Clear the table with the given name."""
        my_cursor = self.db.cursor()
        my_cursor.execute(f"DELETE FROM {table_name}")
        self.db.commit()

    @staticmethod
    def get_insert_queries():
        return (
            ("INSERT INTO repository "
             "(id, year, user, name, creation_date, stars, clone_url)"
             "VALUES (%s, %s, %s, %s, %s, %s, %s)"),
            ("INSERT INTO module "
             "(repo_id, path_rel, name, num_annotations)"
             "VALUES (%s, %s, %s, %s)"),
            ("INSERT INTO func_var "
             "(repo_id, path_rel, name, lineno, num_var, num_var_annotated)"
             "VALUES (%s, %s, %s, %s, %s, %s)"),
            ("INSERT INTO annotation "
             "(repo_id, path_rel, func_var_name, lineno, annot_name, "
             "func_var_type, base_type, entire_annotation, count)"
             "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)")
        )

    def fill_db_with_repos(self):
        """Fill the database with repositories.
        The repositories and their data are read with the module
        read_repository_json.py.
        """
        my_cursor = self.db.cursor()
        repo_handler = read_repository_json.RepoHandler()
        repo_handler.read_repo_files()
        values = list()
        for i, repo in repo_handler.repos:
            values.append(
                (i, repo.get_year(), repo.user, repo.name, repo.created_at,
                 repo.stars, repo.clone_url)
            )
        my_cursor.executemany(self.repo_insert_query, values)
        self.db.commit()

    def get_repo_id(self, year: str, user: str, name: str) -> int:
        """Get the id of a repository.

        Args:
            year (str): Year of creation.
            user (str): Username.
            name (str): Repository name.

        Returns:
            The id of the repository if it exists, else -1.

        Examples:
            >>> db_helper = DBHelper()
            >>> db_helper.connect_to_db()
            >>> db_helper.get_repo_id("2013", "audreyfeldroy",
                    "cookiecutter-pypackage")
            9068
            >>> db_helper.get_repo_id("2022", "machine1337", "fake-sms")
            972
            >>> deb_helper.ger_repo_id("2032", "machine1337", "fake-sms2")
            -1

        """
        my_cursor = self.my_cursor()
        my_cursor.execute(
            f"SELECT id FROM repository WHERE year = {year} AND user = '{user}' "
            f"AND name = '{name}'"
        )
        result = my_cursor.fetchone()
        if result is None:
            return -1
        else:
            return result[0]

    def add_module_to_db(self, id_repo: int, path_rel: str, name: str,
                         num_annotations: int):
        """Called upon by outside module analyzer.py."""
        value = (id_repo, path_rel, name, num_annotations)
        self.module_commits.append(value)

    def get_module(self, id_repo: int, path_rel: str, name: str):
        my_cursor = self.db.cursor()
        my_cursor.execute(
            f"SELECT * FROM module WHERE repo_id = {id_repo} AND "
            f"path_rel = '{path_rel}' AND name = '{name}'"
        )
        return my_cursor.fetchone()

    def add_func_var_to_db(self, repo_id, path_rel, name, lineno, num_var,
                           num_var_annotated):
        """Called upon by outside module analyzer.py."""
        values = (repo_id, path_rel, name, lineno, num_var, num_var_annotated)
        self.func_var_commits.append(values)

    def add_annotation_to_db(self, repo_id, path_rel, func_var_name, lineno,
                             annot_name, func_var_type, base_type,
                             entire_annotation, count):
        """Called upon by outside module analyzer.py."""
        values = (
            repo_id, path_rel, func_var_name, lineno, annot_name,
            func_var_type, base_type, entire_annotation, count
        )
        self.annotation_commits.append(values)

    def save_to_json(self, filename: str):
        data = {
            "module_commits": self.module_commits,
            "func_var_commits": self.func_var_commits,
            "annotation_commits": self.annotation_commits
        }
        with open(filename, "w") as f:
            json.dump(data, f)

    def load_from_json(self, filename: str, verbose: bool = False):
        with open(filename, "r") as f:
            data = json.load(f)
        if verbose:
            print("Loading data for modules... ", end="", flush=True)
        self.module_commits = data["module_commits"]
        if verbose:
            print("Done.\nLoading data for func_vars... ", end="", flush=True)
        self.func_var_commits = data["func_var_commits"]
        if verbose:
            print("Done.\nLoading data for annotations... ", end="", flush=True)
        self.annotation_commits = data["annotation_commits"]
        if verbose:
            print("Done.")

    def safe_insert_commit(self, insert_query, values, verbose: bool = False):
        try:
            self.my_cursor.execute(insert_query, values)
        except mysql.connector.errors.IntegrityError as e:
            if "Duplicate entry" not in e.msg:
                raise e

    def make_commits(self, table: Literal["module", "func_var", "annotation"],
                     verbose: bool = False):
        if verbose:
            print("Committing entries ...")
        if table == "module":
            using = self.module_commits
            using_query = self.module_insert_query
        elif table == "func_var":
            using = self.func_var_commits
            using_query = self.func_var_insert_query
        else:  # table == "annotation"
            using = self.annotation_commits
            using_query = self.annotation_insert_query
        # Set up progress information
        total_queries = len(using)
        current_query = 0
        last_elapsed_time = 0
        for values in using:
            if verbose:
                current_query += 1
                progress = current_query / total_queries
                elapsed_time = time.time() - self.start_time
                estimated_total_time = elapsed_time / progress
                remaining_time = time.strftime("%H:%M:%S", time.gmtime(estimated_total_time - elapsed_time))
                elapsed_time = time.strftime("%H:%M:%S", time.gmtime(elapsed_time))
                # Check if one second has passed since last print
                if elapsed_time != last_elapsed_time:
                    last_elapsed_time = elapsed_time
                    print("Committing module... elapsed time: {} eta: {}, {}% ".format(
                        elapsed_time,
                        remaining_time,
                        round(current_query / total_queries * 100, 2),
                    ))
            self.safe_insert_commit(using_query, values, verbose=verbose)
        self.db.commit()
        if verbose:
            print("Done.")

    def get_num_annotations_from_repo(self, repo_id: int) -> int:
        """Get the number of annotations in a repository.

        Args:
            repo_id (int): The id of the repository.

        Returns:
            The number of annotations in the repository.

        Examples:
            >>> db_helper = DBHelper()
            >>> db_helper.get_num_annotations_from_repo(309)
            0
            >>> db_helper.get_num_annotations_from_repo(310)
            277
            >>> db_helper.get_num_annotations_from_repo(314)
            14894

        """
        my_cursor = self.db.cursor()
        my_cursor.execute(
            f"SELECT annotations_repo FROM repository WHERE id = {repo_id}"
        )
        result = my_cursor.fetchone()
        if result is None:
            return 0
        else:
            return result[0]

    def get_full_annotated_functions(self) -> list:
        """Get all functions that are fully annotated.

        Due to the long runtime of the original SQL query,
        an extra table was set up in mysql to store the results.
        That was done in mysql with the following query:
            CREATE TABLE full_annot AS
            SELECT func_var.repo_id, func_var.path_rel, func_var.name, SUM(func_var.num_var), SUM(func_var.num_var_annotated)
            FROM func_var JOIN annotation
            WHERE num_var_annotated > 1 AND num_var = num_var_annotated AND
            func_var.repo_id = annotation.repo_id AND func_var.path_rel = annotation.path_rel AND
            func_var.name = annotation.func_var_name AND func_var.lineno = annotation.lineno
            GROUP BY func_var.repo_id, func_var.path_rel, func_var.name;
        """
        my_cursor = self.db.cursor()
        my_cursor.execute(
            f"SELECT * FROM full_annot"
        )
        return my_cursor.fetchall()


def main(db: DBHelper, year: int):
    db.load_from_json(f"db_query_{year}.json", verbose=True)
    db.make_commits("module", verbose=True)
    db.make_commits("func_var", verbose=True)
    db.make_commits("annotation", verbose=True)


if __name__ == '__main__':
    db_helper = DBHelper()
    # Initial setup to add all repos to the database
    db_helper.fill_db_with_repos()
    # Before running the next line analyzer.py should have run.
    # That will have stored the data to commit in json files.
    main(db_helper, 2013)
