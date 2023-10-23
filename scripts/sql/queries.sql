### QUANT METHODS
# Overview repo
SELECT * FROM repository;
# WHERE annotations_repo = 52;
SELECT annotations_repo, COUNT(id) FROM repository
WHERE annotations_repo > 0
GROUP BY annotations_repo
ORDER BY annotations_repo DESC;

# Overview modules
SELECT num_annotations, COUNT(*) FROM module
GROUP BY num_annotations;
SELECT COUNT(*) FROM module
WHERE num_annotations > 0;
SELECT num_annotations, COUNT(path_rel) FROM module
WHERE num_annotations > 0
GROUP BY num_annotations
ORDER BY num_annotations DESC;

# Overview func_var
SELECT * FROM func_var
WHERE repo_id = 0
ORDER BY repo_id, path_rel, lineno, name ASC;
SELECT COUNT(*) FROM module
WHERE num_annotations > 0;
SELECT num_annotations, COUNT(path_rel) FROM module
WHERE num_annotations > 0
GROUP BY num_annotations
ORDER BY num_annotations DESC;
# partial annotations
CREATE VIEW partial_annotations AS
SELECT * FROM func_var
WHERE num_var > 1 AND num_var_annotated > 0;

# potential annotations
SET @search_id = 9000;
SELECT SUM(num_var), SUM(num_var_annotated)
FROM func_var
WHERE repo_id >= @search_id AND repo_id < @search_id + 1000;
SELECT COUNT(*)
FROM func_var;

CREATE VIEW partial_annotation_complete AS
SELECT func_var.repo_id, func_var.path_rel, func_var.name, func_var.lineno, func_var.num_var, func_var.num_var_annotated, annotation.func_var_type, annotation.base_type, annotation.entire_annotation, annotation.count
FROM func_var JOIN annotation
WHERE num_var > 1 AND num_var_annotated > 0 AND
func_var.repo_id = annotation.repo_id AND func_var.path_rel = annotation.path_rel AND func_var.name = annotation.func_var_name AND func_var.lineno = annotation.lineno;

SELECT *
FROM partial_annotation_complete;
SELECT annotation.base_type, count(*)
FROM partial_annotation_complete
GROUP BY annotation.base_type;

SELECT func_var.repo_id, func_var.path_rel, func_var.name, SUM(func_var.num_var), SUM(func_var.num_var_annotated)
FROM func_var JOIN annotation
WHERE num_var_annotated > 1 AND num_var = num_var_annotated AND
func_var.repo_id = annotation.repo_id AND func_var.path_rel = annotation.path_rel AND func_var.name = annotation.func_var_name AND func_var.lineno = annotation.lineno
GROUP BY func_var.repo_id, func_var.path_rel, func_var.name;

SELECT annotation.func_var_type, COUNT(*)
FROM func_var JOIN annotation
WHERE num_var > 1 AND num_var_annotated > 0 AND num_var = num_var_annotated AND
func_var.repo_id = annotation.repo_id AND func_var.path_rel = annotation.path_rel AND func_var.name = annotation.func_var_name AND func_var.lineno = annotation.lineno
GROUP BY annotation.func_var_type;


# Overview annotation
SELECT base_type, COUNT(*) AS 'total' FROM annotation
GROUP BY base_type;
SELECT annotation.base_type, COUNT(*) AS 'total' FROM annotation
WHERE func_var_type = 'argument' OR func_var_type = 'return'
GROUP BY annotation.base_type;

SELECT func_var_type, COUNT(*) FROM annotation
GROUP BY func_var_type;
