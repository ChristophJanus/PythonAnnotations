"""A module to analyze the annotations of a GitHub repository.

This module is the main module for analyzing our data. It uses an ast based algorithm to extract annotation, variable
and functions from the GitHub repositories.

The class Annotation provides a framework to store the information about one annotation which will then be stored in
the mysql database.
The class FuncVar has information about a function or variable which can have annotations. The lets as determine how
many annotations could be present if everything was annotated.

AnnotationAnalyzer inherits from ast.NodeVisitor. This function is called on the abstract syntax tree of a module.
It then traverses the tree and extracts all annotations, variables and functions.

"""
import ast
import clipboard
from enum import Enum
import json
import logging
import os
import time
from types import NoneType
from typing import Union, Optional

import mysql.connector.errors

# Own imports
from scripts.sql.db_fill_repos import DBHelper


# This Type was gradually created during testing to find out which annotations are present in the database.
# Correct annotations:
#                   Annot     Ex[Ex]         Ex.Ex          None/ True
TAnnotation = Union[ast.Name, ast.Subscript, ast.Attribute, ast.Constant,
                    # Ann | Ann  func()    Ex1        [T, T]    -4/ ~dtype
                    ast.BinOp, ast.Call, ast.Slice, ast.List, ast.UnaryOp,
                    ast.Tuple,
                    # Incorrect annotations:
                    # T or T  {str: int}
                    ast.BoolOp, ast.Dict, ast.IfExp, ast.Lambda, ast.Set,
                    #            1.0
                    ast.Compare, float, ast.JoinedStr]


class FuncVarType(Enum):
    FUNCTION_ARG = 1
    FUNCTION_RETURN = 2
    VARIABLE = 3


class Annotation:
    """Contains all information about a single annotation.

    Attributes:
        repo_id (int)               : The id of the repository in the database.
        relative_path (str)         : The relative path to the file containing
                the annotation.
        func_var_name (str)         : The name of the function or variable
                containing the annotation.
        lineno (int)                : The line number of the annotation in the file.
        annot_name (str)            : The name of variable/ argument the
                annotation is attached to.
        func_var_type (FuncVarType) : Argument, return or variable.
        base_type (str)             : The base type of the annotation.
                (e.g. "Optional" in x: Optional[Union[str, int]])
        entire_annotation (str)     : Is the entire annotation as string.
        count (int)                 : The total number of types in the
                annotation. (e.g. 4 in x: Optional[Union[str, int]])

    """
    def __init__(self, repo_id: int, relative_path: str, func_var_name: str,
                 lineno: int, annot_name: str, fvt: FuncVarType,
                 base_type: str, entire_annotation: str, count: int):
        self.repo_id: int = repo_id                         # INT
        self.relative_path: str = relative_path             # VARCHAR(270)
        self.func_var_name: str = func_var_name             # VARCHAR(135)
        self.lineno: int = lineno                           # INT
        # If annotation is a function argument, the name of the argument
        # If annotation is a function return, the empty string
        # If annotation is a variable, func_var_name == annot_name
        self.annot_name: str = annot_name                   # VARCHAR(135)
        self.func_var_type: FuncVarType = fvt               # VARCHAR(45)
        self.base_type: str = base_type                     # VARCHAR(45)
        self.entire_annotation: str = entire_annotation     # VARCHAR(540)
        self.count: int = count                             # INT

    def __repr__(self):
        return "Annotation: repo_id: {}, relative_path: {}, " \
            "func_var_name: {}, lineno: {}, annot_name: {}, " \
            "func_var_type: {}, base_type: {}, entire_annotation: {}, " \
            "count: {}".format(
                self.repo_id, self.relative_path,
                self.func_var_name, self.lineno, self.annot_name,
                self.func_var_type, self.base_type, self.entire_annotation,
                self.count)


class FuncVar:
    """A class for a function or a variable which can have annotations.

    Attributes:
        repo_id (int)           : The id of the repository in the database.
        relative_path (str)     : The relative path to the file containing the function/ variable.
        name (str)              : The name of the function or variable containing the annotation.
        lineno (int)            : The line number of the func/ var in the file.
        num_var (int)           : The total number of variables in the function.
                (Arguments and return if exists, for variable it's just 1)
        num_var_annotated (int) : The total number of those variables which are annotated.

    """
    def __init__(self, repo_id: int, rel_path: str, name: str, lineno: int):
        self.repo_id: int = repo_id
        self.relative_path: str = rel_path
        self.name: str = name
        self.lineno: int = lineno
        self.num_var: int = 0
        self.num_var_annotated: int = 0

    def set_func_var_type(self, fvt: FuncVarType):
        self.fvt = fvt

    def increase_num_var(self):
        self.num_var += 1

    def increase_num_var_annotated(self):
        self.num_var_annotated += 1

    def __repr__(self):
        return "FuncVar: repo_id: {}, relative_path: {}, name: {}, " \
            "lineno: {}, num_var: {}, num_var_annotated: {}".format(
                self.repo_id, self.relative_path, self.name, self.lineno,
                self.num_var, self.num_var_annotated)


class AnnotationAnalyzer(ast.NodeVisitor):
    """ast-based analyzer for annotations. Initialized for every module.

    When called on a module, it traverses the abstract syntax tree and extracts all annotations, variables and
    functions. Keeping track of all variables and functions even without annotations allows to infer how much
    could have been annotated.
    AnnotationAnalyzer.visit(module_ast) is called on the abstract syntax tree of a module. That method is provided
    by the ast.NodeVisitor class. It then traverses the tree.
    visit_FunctionDef, visit_AnnAssign and visit_Assign are overriden by this class and will be called during
    the traversal. To extract annotations and other information, separate methods are called.

    Attributes:
        repo_id (int)                   : The id of the repository in the database.
        rel_path (str)                  : The relative path to the module file.
        total_annotations (int)         : The total number of annotations in the module.
        last_count (int)                : The number of types in the last annotation.
        funcs_and_vars (list[FuncVar])  : A list of all functions and variables in the module.
        annotations (list[Annotation])  : A list of all annotations in the module.
        unannotated_names (list[str])   : A list of all argument names that are not annotated.
        logger (logging.Logger)         : A logger to log errors.

    """
    def __init__(self, repo_id: int = -1, rel_path: str = "", progress: float = 0.):
        self.repo_id = repo_id
        self.rel_path = rel_path
        self.total_annotations = 0
        self.last_count = 0
        self.funcs_and_vars: list[FuncVar] = []
        self.annotations: list[Annotation] = []
        self.unannotated_names: list[str] = []
        self.logger = self.init_logger()
        self.progress = progress        # Used to print current progress

    def visit_FunctionDef(self, node: ast.AST):
        """Visit a function definition.
        Extract information about the function and handle annotations if present.
        """
        func_lineno = node.lineno
        # Get function name. "" for functions that don't have a name
        func_name = node.name if node.name else ""
        func = FuncVar(self.repo_id, self.rel_path, func_name, func_lineno)
        # Check if function arguments are annotated
        for arg in node.args.args:
            func.increase_num_var()
            if arg.annotation:
                func.increase_num_var_annotated()
                # Analyze annotation
                self.completely_handle_annotation(
                    annot=arg.annotation,
                    func_var_name=func_name,
                    lineno=func_lineno,
                    fvt=FuncVarType.FUNCTION_ARG,
                    annot_name=arg.arg if arg.arg else ""
                )
        # Check if function return type is annotated
        if node.returns:
            func.increase_num_var()
            func.increase_num_var_annotated()
            self.completely_handle_annotation(
                annot=node.returns,
                func_var_name=func_name,
                lineno=func_lineno,
                fvt=FuncVarType.FUNCTION_RETURN,
                annot_name=""
            )
        # If return is not annotated check if function contains a return
        elif self.contains_return(node.body):
            func.increase_num_var()
        # Check if function is partially annotated
        if 0 < func.num_var_annotated < func.num_var:
            # Get argument names that have no annotation
            for arg in node.args.args:
                self.unannotated_names.append(arg.arg)
        # Add function to list
        self.funcs_and_vars.append(func)
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        var_name = self.get_var_name(node.target)
        # Handle the variable itself
        var = FuncVar(self.repo_id, self.rel_path, var_name, node.lineno)
        var.increase_num_var()
        var.increase_num_var_annotated()
        self.funcs_and_vars.append(var)
        # Handle its annotation
        self.completely_handle_annotation(
            annot=node.annotation,
            func_var_name=var_name,
            lineno=node.lineno,
            fvt=FuncVarType.VARIABLE,
            annot_name=var_name
        )

    def visit_Assign(self, node):
        for target in node.targets:
            # Tuple is for multiple assignments: a, b = 1, 2
            if isinstance(target, ast.Tuple):
                for element in target.elts:
                    name = self.get_var_name(element)
                    var = FuncVar(self.repo_id, self.rel_path, name,
                                  node.lineno)
                    var.increase_num_var()
                    self.funcs_and_vars.append(var)
            # Single assignment: a = 1
            else:
                name = self.get_var_name(target)
                var = FuncVar(self.repo_id, self.rel_path, name,
                              node.lineno)
                var.increase_num_var()
                self.funcs_and_vars.append(var)
        self.generic_visit(node)

    def completely_handle_annotation(self, annot: TAnnotation,
                                     func_var_name: str,
                                     lineno: int,
                                     fvt: FuncVarType,
                                     annot_name: str):
        self.total_annotations += 1
        # handle_annotation was initially created and expanded to investigate which types could be present
        # self.handle_annotation(annot)
        # handle_annotation_basic was later used in the main analysis to count the number of types in an annotation:
        # Optional[Union[str, int]] -> 4
        self.handle_annotation_basic(annot)
        # last_count attribute is used to count the number types in an annotation. See example above.
        self.last_count = 0
        # Create annotation object to later store in database
        annot = Annotation(
            repo_id=self.repo_id,
            relative_path=self.rel_path,
            func_var_name=func_var_name,
            lineno=lineno,
            annot_name=annot_name,
            fvt=fvt,
            base_type=self.get_base_type(ast.unparse(annot)),
            entire_annotation=ast.unparse(annot),
            count=self.last_count
        )
        self.annotations.append(annot)

    def handle_annotation_basic(self, annotation: TAnnotation):
        """Count the number of types in an annotation.
        Optional[Union[str, int]] -> 4
        """
        # Found a type
        if isinstance(annotation, ast.Name) or isinstance(annotation,
                                                          ast.Constant):
            self.last_count += 1
        # Correctly traverse annotation ast
        elif isinstance(annotation, ast.Subscript):
            self.handle_annotation_basic(annotation.value)
            self.handle_annotation_basic(annotation.slice)
        elif isinstance(annotation, ast.Attribute):
            self.handle_annotation_basic(annotation.value)
        elif isinstance(annotation, ast.BinOp):
            self.handle_annotation_basic(annotation.left)
            self.handle_annotation_basic(annotation.right)
        elif isinstance(annotation, ast.Call):
            self.handle_annotation_basic(annotation.func)
        elif isinstance(annotation, ast.Slice):
            if annotation.lower:
                self.handle_annotation_basic(annotation.lower)
            if annotation.upper:
                self.handle_annotation_basic(annotation.upper)
        elif isinstance(annotation, ast.Tuple) or \
                isinstance(annotation, ast.List):
            for element in annotation.elts:
                self.handle_annotation_basic(element)
        elif isinstance(annotation, ast.UnaryOp):
            self.handle_annotation_basic(annotation.operand)

    @staticmethod
    def contains_return(body) -> bool:
        """Check if a function contains a return statement.
        Only check for return statements that return something. return / return None do not need to be annotated.
        """
        for statement in body:
            if (isinstance(statement, ast.Return) and
                    statement.value is not None and not
                    (isinstance(statement.value, ast.Constant) and
                     statement.value.value is None)):
                return True
        return False

    @staticmethod
    def get_var_name(element: ast.AST) -> str:
        """Get the name of a variable from an ast element."""
        name = ""
        if isinstance(element, ast.Name):
            if element.id:
                name = element.id
        elif isinstance(element, ast.Attribute):
            if element.attr:
                name = element.attr
        elif isinstance(element, ast.Subscript):
            return AnnotationAnalyzer.get_var_name(element.value)
        return name

    @staticmethod
    def check_constant(annot: Union[ast.Constant, ast.UnaryOp]) -> bool:
        """Used to check if an annotation is a constant.
        Constants either are ast.Constant ("hello") or ast.UnaryOp with ast.USub and then ast.Constant (-1).
        """
        # Check if it either is a constant: 1, "hello", True, None
        if isinstance(annot, ast.Constant):
            return True
        # or a negative constant: -1, -2, -3
        if isinstance(annot, ast.UnaryOp):
            if not isinstance(annot.op, ast.USub):
                return False
            if not isinstance(annot.operand, ast.Constant):
                return False
            return True
        return False

    @staticmethod
    def get_base_type(unparsed_annotation: Optional[str]):
        """Get the base type of given annotation.
        Returns either the python type or user defined.

        Args:
            unparsed_annotation (str): The annotation as string.

        Examples:
            >>> AnnotationAnalyzer().get_base_type(None)
            ''
            >>> AnnotationAnalyzer().get_base_type("")
            ''
            >>> AnnotationAnalyzer().get_base_type("int")
            'int'
            >>> AnnotationAnalyzer().get_base_type("Optional[Union[str, int]]")
            'Optional'
            >>> AnnotationAnalyzer().get_base_type("Callable[]")
            'Callable'
            >>> AnnotationAnalyzer().get_base_type("ImportedClass")
            'user_defined'

        """
        if not unparsed_annotation:
            return ""
        # Look at string before first '[' or ',' or ' '
        base_type = (
            unparsed_annotation.split('[')[0].split(',')[0].split(' '))[0]
        # Check if base type is a python type
        if base_type in ["None", "bool", "int", "float", "complex", "str",
                         "bytes", "bytearray", "memoryview", "range",
                         "tuple", "list", "set", "frozenset", "dict",
                         "ellipsis", "...", "type", "object",
                         "NoneType", "Any", "Union", "Optional", "Callable",
                         "TypeVar", "Generic", "ClassVar", "Final",
                         "Literal", "Annotated", "TypedDict", "Protocol",
                         "runtime_checkable", "AbstractSet"]:
            if base_type == "...":
                base_type = "ellipsis"
            return base_type
        else:
            return "user_defined"

    def handle_annotation(self, annotation: TAnnotation,
                          verbose: Union[bool, str] = False):
        # debug help
        if verbose == "full":
            print("{}% L: {}, A: {}".format(
                self.progress, annotation.lineno, annotation))
        # This was used during testing to quickly debug to a specific line which caused an error.
        if annotation.lineno in [1, 4, 7, 10]:
            pass  # break point
        # Check correctness of self defined types
        if not isinstance(annotation, TAnnotation):
            self.log_error("Error at line {}: ".format(annotation.lineno) +
                           "annotation is of unexpected type: " +
                           repr(type(annotation)))
        # annotation is a Name
        elif isinstance(annotation, ast.Name):
            # print(f"Found annotation: {annotation.id}")
            self.last_count += 1
        # annotation is a Subscript
        elif isinstance(annotation, ast.Subscript):
            self.handle_annotation(annotation.value)
            self.handle_annotation(annotation.slice)
        # Annotation is an attribute
        elif isinstance(annotation, ast.Attribute):
            self.handle_annotation(annotation.value)
            if not isinstance(annotation.attr, str):
                self.log_error("Error at line {}: ".format(annotation.lineno) +
                               "Attribute annotation, attr is not string.")
                return
        # Annotation is a constant value
        elif isinstance(annotation, ast.Constant):
            self.last_count += 1
            possible_constant_types = \
                Union[NoneType, bool, type(...), str, int, float, bytes]
            if not isinstance(annotation.value, possible_constant_types):
                self.log_error("Error at line {}: ".format(annotation.lineno) +
                               "Constant annotation is of unexpected type: " +
                               repr(type(annotation.value)) + " and value: " +
                               repr(annotation.value))
        # Annotation is a binary operation: type | type (Union[type, type])
        elif isinstance(annotation, ast.BinOp):
            self.handle_annotation(annotation.left)
            self.handle_annotation(annotation.right)
        # Annotation is a function call
        elif isinstance(annotation, ast.Call):
            # Get function name
            self.handle_annotation(annotation.func)
        # Annotation is a slice T["bs"...,2]
        elif isinstance(annotation, ast.Slice):
            if annotation.lower:
                self.handle_annotation(annotation.lower)
            if annotation.upper:
                self.handle_annotation(annotation.upper)
        # Annotation is a list
        # Potentially: [type, type] instead of list[type]
        # or correct from torchtyping: [type, type, type]
        elif isinstance(annotation, ast.List):
            for element in annotation.elts:
                self.handle_annotation(element)
        # Annotation is a unary operation: ~dtype or -4 before constant
        elif isinstance(annotation, ast.UnaryOp):
            if not isinstance(annotation.op, ast.USub) and \
                    not isinstance(annotation.op, ast.Invert):
                self.log_error("Error at line {}: ".format(annotation.lineno) +
                               "UnaryOp annotation is of unexpected type:" +
                               repr(type(annotation.op)))
            self.handle_annotation(annotation.operand)
        elif isinstance(annotation, ast.Tuple):
            for element in annotation.elts:
                self.handle_annotation(element)
        # ### Now follow incorrect annotations
        # Annotation is a boolean operation: type or type (Union[type, type])
        elif isinstance(annotation, ast.BoolOp):
            if not (isinstance(annotation.op, ast.Or) or
                    isinstance(annotation.op, ast.And)):
                self.log_error("Error at line {}: ".format(annotation.lineno) +
                               "BoolOp annotation is of unexpected type:" +
                               repr(type(annotation.op)))
        # Incorrect annotation: {str: int}
        elif isinstance(annotation, ast.Dict):
            pass
        # Incorrect annotation T if is_something() else Any
        # instead of Union[T, Any]
        elif isinstance(annotation, ast.IfExp):
            pass
        # Incorrect annotation: lambda x: x
        elif isinstance(annotation, ast.Lambda):
            pass
        # Incorrect annotation: {str, int}
        elif isinstance(annotation, ast.Set):
            pass
        # Incorrect annotation: x: int <= 1024
        # instead of x: int and later assert x <= 1024
        elif isinstance(annotation, ast.Compare):
            pass
        elif isinstance(annotation, float):
            pass
        elif isinstance(annotation, ast.JoinedStr):
            pass
        else:
            self.log_error("HELL-Error at line {}: ".format(annotation.lineno) +
                           "annotation is of unexpected type:" +
                           repr(type(annotation)))

    @staticmethod
    def init_logger() -> logging.Logger:
        new_logger = logging.getLogger("my_logger")
        new_logger.setLevel(logging.ERROR)
        handler = logging.FileHandler("error_log.txt", "w", "utf-8")
        handler.setLevel(logging.ERROR)
        formatter = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")
        handler.setFormatter(formatter)
        new_logger.addHandler(handler)
        return new_logger

    def log_error(self, err_msg: str):
        self.logger.error("\nError in file: " + clipboard.paste() + "\n"
                          "Error message: " + err_msg + "\n")


def main_analyzer():
    """This function was used to initially test the analyzer and to find out which annotations are present in the
    repositories."""
    # Initialize
    start_time = time.time()
    db_helper = DBHelper()
    # Go through the entire database
    traverse_database(db=db_helper, start_time=start_time, verbose=True)


def traverse_database(db: Optional[DBHelper] = None, start_time: float = 0,
                      verbose: Union[bool, str] = False):
    """This function goes through every year, user and repository in the database and calls analyze_repository() on
    every repository."""
    # Get the parent folder of all repositories
    repos_folder: str = get_repo_path()
    # Init variables for progress calculation
    total_repos: int = 1000
    current_repo: int = 0
    last_progress: float = 0
    # Initial progress print
    if verbose and verbose != "full":
        print(f"0%")
    # Go through every year
    for year in os.listdir(repos_folder):
        year_folder: str = os.path.join(repos_folder, year)
        # Go through every user
        for user in os.listdir(year_folder):
            user_folder: str = os.path.join(year_folder, user)
            # Go through every repo
            for repo in os.listdir(user_folder):
                # Calculate progress
                current_repo += 1
                # Progress calculation
                progress = round(current_repo / total_repos * 100, 2)
                elapsed_time = time.time() - start_time
                estimated_total_time = elapsed_time / (progress / 100)
                remaining_time = estimated_total_time - elapsed_time
                # convert to readable time
                remaining_time = time.strftime("%H:%M:%S",
                                               time.gmtime(remaining_time))
                elapsed_time = time.strftime("%H:%M:%S",
                                             time.gmtime(elapsed_time))
                if verbose and verbose != "full" and \
                        progress > last_progress:
                    print(f"{progress}%, elapsed time: {elapsed_time}, eta: {remaining_time}")
                last_progress = progress
                # Get repo id in database
                id_repo: int = -1
                if db:
                    id_repo = db.get_repo_id(year, user, repo)
                    if id_repo == -1:
                        exit(f"Error: Repo {year}/{user}/{repo} not found in "
                             f"database.")
                repo_folder: str = os.path.join(user_folder, repo)
                # Check repo for annotations
                if db:
                    analyze_repository(repo_folder, id_repo, db, progress, False)
                if verbose == "full":
                    print(f"{progress}%   Checking repo: {repo_folder}:",
                          flush=True)
                analyze_repository(repo_folder, id_repo, db, progress, False)
                if verbose == "full":
                    print(f"{progress}%   Done.", flush=True)
        db.save_to_json("sql/db_query_" + year + ".json")


def get_repo_path() -> str:
    """Construct the path to the 'repos' folder.
    It is the folder where alle the repositories are stored."""
    repos_folder: str = os.getcwd()
    if os.path.basename(repos_folder) == "scripts":
        repos_folder = os.path.dirname(os.getcwd())
    elif os.path.basename(repos_folder) == "github":
        repos_folder = os.path.join(os.getcwd(), "data")
    return os.path.join(repos_folder, "repos")


def analyze_repository(repo_folder: str, id_repo: int,
                       db: Optional[DBHelper] = None,
                       progress: float = 0.,
                       verbose: bool = False):
    """Analyze a given GitHub repository.
    Add annotations into the database.

    Args:
        repo_folder (str)       : Path to the repository folder.
        id_repo (int)           : The id of the repository in the database.
        progress (float)        : The current progress in percent.
        db (DBHelper, optional) : Database connection. Defaults to None.
        verbose (bool)          : Print progress. Defaults to False.

    """
    for root, dirs, files in os.walk(repo_folder):
        # Ignore the following folders
        ignored_folders = ["mypy", "python2.6"]
        for folder in ignored_folders:
            if folder in dirs:
                dirs.remove(folder)
        # Check all files
        for file in files:
            # Ignore non-python files
            file_path: str = os.path.join(root, file)
            relative_file_path: str = file_path.replace(repo_folder + '/', "")
            if not file.endswith(".py") and not file.endswith(".pyi"):
                continue
            # Ignore stub files without corresponding python file
            if file.endswith(".pyi") and file[:-1] not in files:
                continue
            try:
                with open(file_path) as f:
                    code = f.read()
            except (FileNotFoundError, UnicodeDecodeError):
                continue
            try:
                node = ast.parse(code)
                if verbose:
                    print(f"{progress}%    Checking file: {file_path}.. ",
                          end="")
                # Copy file path to clipboard in case it fails
                # clipboard.copy(file_path)
                # Initiate analyzer
                repo_annotations = AnnotationAnalyzer(id_repo, relative_file_path, progress)
                # Check annotations
                repo_annotations.visit(node)
                # CHECKING CALCULATIONS
                total_annotated = len(repo_annotations.annotations)
                total_func_vars_annotated = 0
                for func_var in repo_annotations.funcs_and_vars:
                    total_func_vars_annotated += func_var.num_var_annotated
                if repo_annotations.total_annotations != total_annotated:
                    print(f"Error: total_annotations: "
                          f"{repo_annotations.total_annotations} "
                          f"!= total_annotated: {total_annotated}")
                if total_func_vars_annotated != total_annotated:
                    print(f"Error: total_func_vars_annotated: "
                          f"{total_func_vars_annotated} "
                          f"!= total_annotated: {total_annotated}")
                # Add module to db
                if not db:
                    continue
                try:
                    relative_file_path = relative_file_path[:269]
                    db.add_module_to_db(id_repo, relative_file_path, file,
                                        repo_annotations.total_annotations)
                except mysql.connector.errors.IntegrityError as e:
                    # Module already exists in db
                    if "Duplicate entry" not in e.msg:
                        raise e
                # Add functions and variables to db
                for func_var in repo_annotations.funcs_and_vars:
                    func_var = verify_name_length(func_var)
                    try:
                        db.add_func_var_to_db(
                            func_var.repo_id, func_var.relative_path,
                            func_var.name, func_var.lineno, func_var.num_var,
                            func_var.num_var_annotated
                        )
                    except mysql.connector.errors.IntegrityError as e:
                        # Functions/ variables already exists in db
                        if "Duplicate entry" not in e.msg:
                            raise e
                # Add annotations to db
                convert_fvt_to_str(repo_annotations.annotations)
                for annot in repo_annotations.annotations:
                    annot = verify_name_length(annot)
                    try:
                        db.add_annotation_to_db(
                            annot.repo_id, annot.relative_path,
                            annot.func_var_name, annot.lineno,
                            annot.annot_name, annot.func_var_type,
                            annot.base_type, annot.entire_annotation,
                            annot.count
                        )
                    except mysql.connector.errors.IntegrityError as e:
                        # Annotations already exists in db
                        if "Duplicate entry" not in e.msg:
                            raise e
                if verbose:
                    print("Done.")
            except SyntaxError:
                if verbose:
                    print(f"SyntaxError in file {file_path}")
            except ValueError:
                if verbose:
                    print(f"ValueError in file {file_path}")
            except RecursionError:
                if verbose:
                    print(f"RecursionError in file {file_path}")
            except UnboundLocalError:
                if verbose:
                    print(f"UnboundLocalError in file {file_path}")


def convert_fvt_to_str(annotations):
    """Converting enum FuncVarType to string ot print to database."""
    for annotation in annotations:
        if annotation.func_var_type == FuncVarType.FUNCTION_ARG:
            annotation.func_var_type = "argument"
        elif annotation.func_var_type == FuncVarType.FUNCTION_RETURN:
            annotation.func_var_type = "return"
        elif annotation.func_var_type == FuncVarType.VARIABLE:
            annotation.func_var_type = "variable"
        else:
            raise ValueError("Unknown FuncVarType: " +
                             repr(annotation.func_var_type))


def verify_name_length(obj: Union[FuncVar, Annotation]) -> Union[FuncVar, Annotation]:
    """Limiting length of strings to apply with database constraints."""
    if isinstance(obj, FuncVar):
        obj.relative_path = obj.relative_path[:269]
        obj.name = obj.name[:134]
    elif isinstance(obj, Annotation):
        obj.relative_path = obj.relative_path[:269]
        obj.func_var_name = obj.func_var_name[:134]
        obj.annot_name = obj.annot_name[:134]
        obj.func_var_type = obj.func_var_type[:44]
        obj.base_type = obj.base_type[:44]
        obj.entire_annotation = obj.entire_annotation[:539]
    return obj


def main_test():
    """This function is called when the analyzer exited with an error on a file.
    The last file is automatically copied to the clipboard and the path can be copied here."""
    with open("../../repos/2013/nucleic/atom/atom/scalars.pyi") as f:
        code = f.read()
    node = ast.parse(code)
    repo_annotations = AnnotationAnalyzer()
    repo_annotations.visit(node)
    print("Repo: repo_id: {}, relative_path: {}, name: {}, "
          "num_annotations: {}".format(
            repo_annotations.repo_id, repo_annotations.rel_path,
            "read_repository_json.py", repo_annotations.total_annotations))
    print("\nFunctions and Variables:")
    for func_var in repo_annotations.funcs_and_vars:
        print(" ", func_var)
    print("\nAnnotations:")
    for annotation in repo_annotations.annotations:
        print(" ", annotation)


def main_unannotated():
    json_path = "unannot.json"
    # Build
    # for repo in repo_list:
    #     d = get_unannotated_arg_names(id_repo=repo[0], repo_path=repo[1], unannotated_names_dict=d)
    # Get number of unannotated arguments
    write_dict_to_json(d, json_path)
    d = load_from_json_to_dict(json_path)
    d = {k: v for k, v in sorted(d.items(), key=lambda item: item[1], reverse=True)}
    total = 0
    for _, value in d.items():
        total += value
    for key, value in d.items():
        print(key, value, total, round(value / total * 100, 2))


def get_unannotated_arg_names(id_repo: int, repo_path: str,
                              unannotated_names_dict: dict) -> dict:
    # Ignore the following folders
    ignored_folders = ["mypy", "python2.6"]
    for root, dirs, files in os.walk(repo_path):
        for folder in ignored_folders:
            if folder in dirs:
                dirs.remove(folder)
        for file in files:
            # Ignore non-python files
            file_path: str = os.path.join(root, file)
            if not file.endswith(".py") and not file.endswith(".pyi"):
                continue
            # Ignore stub files without corresponding python file
            if file.endswith(".pyi") and file[:-1] not in files:
                continue
            try:
                with open(file_path) as f:
                    code = f.read()
            except (FileNotFoundError, UnicodeDecodeError):
                continue
            try:
                node = ast.parse(code)
                # Copy file path to clipboard in case it fails
                # clipboard.copy(file_path)
                # Initiate analyzer
                repo_annotations = AnnotationAnalyzer(id_repo, repo_path)
                # Check annotations
                repo_annotations.visit(node)
                for unannot_name in repo_annotations.unannotated_names:
                    if unannot_name not in unannotated_names_dict:
                        unannotated_names_dict[unannot_name] = 1
                    else:
                        unannotated_names_dict[unannot_name] += 1
            except (SyntaxError, ValueError, RecursionError, UnboundLocalError):
                pass
    return unannotated_names_dict


def write_dict_to_json(d: dict, file_name: str):
    with open(file_name, "w") as f:
        json.dump(d, f)


def load_from_json_to_dict(file_name) -> dict:
    with open(file_name, "r") as f:
        return json.load(f)


if __name__ == "__main__":
    pass
