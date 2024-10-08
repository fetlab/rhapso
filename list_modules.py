import ast


def list_modules(*files):
	modules = set()

	def visit_Import(node):
			for name in node.names:
					modules.add(name.name.split(".")[0])

	def visit_ImportFrom(node):
			# if node.module is missing it's a "from . import ..." statement
			# if level > 0 it's a "from .submodule import ..." statement
			if node.module is not None and node.level == 0:
					modules.add(node.module.split(".")[0])

	node_iter = ast.NodeVisitor()
	node_iter.visit_Import = visit_Import
	node_iter.visit_ImportFrom = visit_ImportFrom

	for fn in files:
		with open(fn) as f:
			node_iter.visit(ast.parse(f.read()))

	return modules

if __name__ == "__main__":
	import sys, pkgutil
	from pathlib import Path
	allmods = {p.name for p in pkgutil.iter_modules() if Path(p.module_finder.path) != Path.cwd()}
	modules = [m for m in list_modules(*sys.argv[1:]) if m not in allmods]
	print("modules:" , '\n'.join(sorted(modules)))
