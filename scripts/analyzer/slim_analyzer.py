"""This module was used for the mypy anylysis in the thesis."""
import ast
import json
import mypy.api
import os
import typing
# Own module
from scripts.sql.db_fill_repos import DBHelper


basic_types = ["int", "float", "complex", "str", "bool"]


class FunctionFinder(ast.NodeVisitor):
    def __init__(self, function_name: str):
        self.function_name = function_name
        self.fount_function = None

    def visit_FunctionDef(self, node):
        if self.fount_function:
            return
        if node.name == self.function_name:
            self.fount_function = node
            return
        self.generic_visit(node)


def get_annotation_name(node):
    if isinstance(node, ast.Name):
        if node.id in basic_types:
            return node.id
        return "ERROR"
    # Check if it is a literal
    elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "Literal" and \
            isinstance(node.slice, ast.Constant):
        return node.slice.value
    # Check if it is Optional
    elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "Optional":
        return get_annotation_name(node.slice)
    # Check if it is a Union
    elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "Union":
        if isinstance(node.slice, ast.Tuple):
            for element in node.slice.elts:
                ret_for_el = get_annotation_name(element)
                if ret_for_el != "ERROR":
                    return ret_for_el
    elif isinstance(node, ast.Constant):
        try:
            if node.value and 'dict' in node.value:  # Faulty type annotation
                return "ERROR"
        except TypeError:
            return "ERROR"
        return node.value
    else:
        return "ERROR"


def get_function_ast(file_path: str, function_name: str) -> ast.FunctionDef:
    finder = FunctionFinder(function_name)
    try:
        with open(file_path, "r") as f:
            code = f.read()
    except FileNotFoundError:
        return
    try:
        tree = ast.parse(code)
        finder.visit(tree)
        return finder.fount_function
    except (SyntaxError, ValueError, RuntimeError, UnboundLocalError):
        return


def get_function_info(function_ast: ast.FunctionDef) -> (dict, str):
    # Get arguments and their type annotations
    args = {arg.arg: get_annotation_name(arg.annotation)
            for arg in function_ast.args.args if arg.annotation is not None}

    # Get return type annotation
    returns = get_annotation_name(function_ast.returns) if function_ast.returns else None

    return args, returns


def create_argument_dict(args: dict) -> typing.Optional[dict]:
    for arg in args:
        if args[arg] == "ERROR":
            return None
        elif isinstance(args[arg], str):
            if args[arg] == "int":
                args[arg] = 10
            elif args[arg] == "float":
                args[arg] = 2.0
            elif args[arg] == "complex":
                args[arg] = 1j
            elif args[arg] == "str":
                args[arg] = "something"
            elif args[arg] == "bool":
                args[arg] = True
            elif args[arg] == "None":
                args[arg] = None
            else:
                return None
    return args


def run_function(function_ast, args):
    # Convert AST to code
    code = compile(ast.Module(body=[function_ast], type_ignores=[]), filename="<ast>", mode="exec")

    # Create a new namespace and execute the function
    namespace = {"Literal": typing.Literal}
    exec(code, namespace)

    # Run the function with the provided arguments
    return namespace[function_ast.name](**args)


def my_type_check_function(function_ast: ast.FunctionDef):
    # Get the function arguments and return type
    args, returns = get_function_info(function_ast)

    # Create a dictionary with the arguments and their values
    args = create_argument_dict(args)

    # If the arguments could not be created, skip the function
    if args is None:
        return "Arguments could not be created", args

    # Run the function with the arguments
    try:
        res = run_function(function_ast, args)
    except TypeError as e:
        if "missing" in str(e) and ("required positional argument" in str(e),
                                    "required keyword-only argument" in str(e)):
            return "Missing", e.args
        else:
            return "MeinTypeError!", e.args
    except (NameError, NotImplementedError, ImportError, AttributeError, ValueError, RuntimeError, UnboundLocalError,
            SyntaxError, FileNotFoundError, IndexError, KeyError, ZeroDivisionError, AssertionError) as e:
        return "BadError!", e.args

    # Check return has the correct type
    if returns == "ERROR":
        return "ERROR!", "No trivial return type"
    elif not isinstance(returns, str):
        return res == returns, (res, returns)
    else:
        return isinstance(res, eval(returns)), (res, returns)


def load_from_json(file_name: str) -> typing.Union[dict, list]:
    with open(file_name, 'r') as f:
        return json.load(f)


def store_to_json(file_name: str, data: dict):
    with open(file_name, 'w') as f:
        json.dump(data, f)


def get_repo_from_file_path(file_path: str) -> str:
    directories = file_path.split(os.sep)
    # Get parent directory:
    return os.sep.join(directories[:12])


def get_repos_to_check(full_list: list, last_repo_checked: int):
    repos_to_check = []
    for repo_id, file_path, _, _, _ in full_list:
        repo_path = get_repo_from_file_path(file_path)
        if repos_to_check and repos_to_check[-1][0] == repo_id:
            continue
        repos_to_check.append((repo_id, repo_path))
    return repos_to_check


def handle_mypy_file(repo_path: str) -> bool:
    result = mypy.api.run([repo_path,
                           "--show-error-codes", "--namespace-packages",
                           "--ignore-missing-imports", "--show-column-numbers"])
    if result[0]:  # Mypy found TypeError
        return False
    else:           # Mypy did not find TypeError
        return True


def handle_mypy_file_with_return(repo_path: str) -> typing.Optional:
    result = mypy.api.run([repo_path,
                           "--show-error-codes", "--namespace-packages",
                           "--ignore-missing-imports", "--show-column-numbers"])
    return result[0]


def main_mypy(full_list, verbose: bool = False):
    handled_repo_json_file_path = "mypy_progress.json"
    handled_repos: dict[int, bool] = load_from_json(handled_repo_json_file_path)
    # Get highest number already checked
    current_repo_id = 7066
    repos_to_check = get_repos_to_check(full_list, 0)
    total_repos = len(full_list)
    for repo in repos_to_check:
        if repo[0] <= current_repo_id:
            continue
        if verbose:
            current_repo_id = repo[0]
            print("{}% Checking repo: {}/{}".format(round(current_repo_id / 100, 2),
                                                    current_repo_id, 10000))
        all_fine = handle_mypy_file(repo[1])
        handled_repos[repo[0]] = all_fine
        store_to_json(handled_repo_json_file_path, handled_repos)


def main():
    verbose: bool = True
    # Get fully annotated functions from database
    if verbose:
        print("Getting fully annotated functions from database...", end="")
    db = DBHelper()
    full_list = db.get_full_annotated_functions()
    exit(len(full_list))
    # Check all functions with my checker
    if verbose:
        print("Done.")
    # Get mypy to check all files
    # mypy checks already done
    handled_repo_json_file_path = "mypy_progress.json"
    handled_repos: dict[str, bool] = load_from_json(handled_repo_json_file_path)
    # main_mypy(full_list, verbose=True)
    last_progress = .0
    important_repo_stuff = []
    # Go through each function
    for i, func in enumerate(full_list):
        if func[0] in [191, 2158, 2023, 5075, 5312]:
            continue
        if func[0] == 6005 and func[2] == "_resource_arn":
            pass
        else:
            continue
        # Look for repositories that were type correct according to mypy
        try:
            mypy_fine = handled_repos[repr(func[0])]
        except KeyError:
            mypy_fine = False
        if not mypy_fine:
            continue
        if verbose:
            progress = round(i / len(full_list) * 100, 1)
            # if progress > last_progress:
            last_progress = progress
            print("{}%: Checking id: {}/{}: {}".format(progress, func[0], 10000, func[2]))
        # Get the function AST
        function_ast = get_function_ast(func[1], func[2])
        if function_ast is None:
            continue
        # Check the function with random arguments
        my_check = my_type_check_function(function_ast)
        if my_check is False or (isinstance(my_check[0], str) and "MeinTypeError!" in my_check[0]):  # or True:
            try:
                important_repo_stuff.append((func[0], func[1], func[2], my_check))
            except TypeError:
                pass
        # try:
        #     store_to_json("D:\\Chris\\Documents\\Uni\\23_SoSe\\Bachelorarbeit\\github\\data\\scripts\\important_repo_stuff.json",
        #                   important_repo_stuff)
        # except TypeError:
        #     important_repo_stuff.pop()


def manual_type_check():
    # Import files greenlight by mypy
    file_list = load_from_json("mypy_no_error_repos.json")
    # Get repositories
    file_set = set()
    for file in file_list:
        file_set.add(get_repo_from_file_path(file[1]))
    repo_list = list(file_set)
    # Double check mypy results
    for repo in repo_list:
        mypy_result = handle_mypy_file_with_return(repo)
        print("{}: {}".format(repo, mypy_result))
    # Check function with default types
    for file in file_list:
        function_ast = get_function_ast(file[1], file[2])
        if function_ast is None:
            continue
        my_check = my_type_check_function(function_ast)
        if not my_check:
            print("{}: {}".format(file[2], my_check))
            input()


def trying_functions():
    def _resource_arn(name: str, pattern: str, account_id: str = None, region_name: str = None) -> str:
        if ":" in name:
            return name
        account_id = account_id
        region_name = region_name
        if len(pattern.split("%s")) == 3:
            return pattern % (account_id, name)
        return pattern % (region_name, account_id, name)
    arguments = {"int": 10, "float": 2.0, "complex": 1j, "str": "something", "bool": True, "None": None}
    name = arguments["str"]
    pattern = arguments["str"]
    account_id = arguments["str"]
    region_name = arguments["str"]
    print(_resource_arn(name, pattern, account_id, region_name))


if __name__ == '__main__':
    main()
