#!/usr/bin/python3

import sys
import re
import inspect
from ast import literal_eval
from getopt import getopt
from os import path, listdir, makedirs
from types import ModuleType
from shutil import rmtree

def clean_code(orig, depth):
    code = ""
    includes = []
    excludes = []
    all_var = []
    has_all = False
    line = orig.readline()
    while True:
        if not line:
            break
        
        if re.search(r'"""', line):
            code += line
            if re.search(r'""".*"""', line):
                line = orig.readline()
            else:
                while True:
                    line = orig.readline()
                    code += line
                    if re.search(r'"""', line):
                        line = orig.readline()
                        break
        elif re.search(r"^(def|class) ", line):
            code += line
            while True:
                line = orig.readline()
                if re.search(r"^    ", line):
                    code += line
                elif not re.search(r"#", line):
                    break
        elif re.search(r"^import .+? as ", line.strip()):
            excludes.append(re.sub(r"^import .+? as (.+)", r"\1", line.strip()))
            includes.append((re.sub(r"^import (.*?)[^\.] as .+", r"\1", line.strip()),
                [(re.sub(r"^import .*?([^\.]) as .+", r"\1", line.strip()), excludes[-1])]))
            line = orig.readline()
        elif re.search(r"from .+? import .+", line.strip()):
            if re.search(r".+? as .+", line.strip()):
                excludes.append(re.sub(r".+? as (.+)", r"\1", line.strip()))
                includes.append((re.sub(r"^from (.+?) import .+? as .+", r"\1", line.strip()),
                    [(re.sub(r"^from .+? import (.+?) as .+", r"\1", line.strip()), excludes[-1])]))
            elif not re.search(r"from \. import", line.strip()):
                names = re.split(r" *, *", re.sub(r".+? import (.+)", r"\1", line.strip().strip(",")))
                excludes += names
                includes.append((re.sub(r"^from (.+?) import .+", r"\1", line.strip()), [(name, name) for name in names]))
            line = orig.readline()
        elif re.search(r"__all__", line):
            has_all = True
            all_var += literal_eval(re.sub(r".*(\[.*\]).*", r"\1", line))
            line = orig.readline()
        else:
            line = orig.readline()
    
    i = 0
    while i < len(includes):
        if len(re.sub(r"^(\.*).*", r"\1", includes[i][0])) not in range(1, depth + 1):
            del includes[i]
            i -= 1
        else:
            if has_all:
                j = 0
                while j < len(includes[i][1]):
                    if includes[i][1][j][1] not in all_var or includes[i][1][j][1].startswith("_"):
                        del includes[i][1][j]
                        j -= 1
                    j += 1
                if len(includes[i][1]) == 0:
                    del includes[i]
                    i -= 1
        i += 1
    
    return code, includes, excludes

def import_code(f_path, depth):
    if f_path.endswith(".py"):
        name = path.splitext(path.basename(f_path))[0]
    else:
        name = path.basename(f_path)
        f_path = path.join(f_path, "__init__.py")
    
    f = open(f_path, 'r', encoding="utf-8")
    code, incs, excs = clean_code(f, depth)
    f.close()
    mod = ModuleType(name)
    exec(code, mod.__dict__)
    return mod, incs, excs

def find_imp(root, imp, depth):
    f = open(path.join(root, "__init__.py"), 'r', encoding="utf-8")
    n_imp = None
    for line in f:
        if re.search(r"from \..*? import .+? as {}".format(re.escape(imp)), line):
            n_imp = re.sub(r"from (.+?) import (.+?) as .+", r"\1.\2", line.strip())
            break
        elif re.search(r"import \..+? as {}".format(re.escape(imp)), line):
            n_imp = re.sub(r"import (.+?) as .+", r"\1", line.strip())
            break
        elif re.search(r"from \..+? import.*[ ,]{}(?:[ ,]|$)".format(re.escape(imp)), line):
            n_imp = re.sub(r"from (.+?) import .+", r"\1.{}".format(imp), line.strip())
            break
    f.close()
    if n_imp is None:
        return None
    if len(re.sub(r"^(\.+).*", r"\1", n_imp)) > depth:
        return False
    return n_imp

def resolve_imp(root, imp, depth):
    if not path.isfile(path.join(root, "__init__.py")):
        return None, None
    start = len(re.sub(r"^(\.+).*", r"\1", imp))
    root = path.join(root, *[".."]*(start - 1))
    depth -= start - 1
    imps = imp.strip(".").split(".")
    for i, imp in enumerate(imps):
        n_imp = find_imp(root, imp, depth) if i != 0 else None
        if n_imp == False:
            return None, None
        elif n_imp is not None:
            root, depth = resolve_imp(root, n_imp, depth)
            if root is None:
                return None, None
        else:
            root = path.join(root, imp)
            if path.isfile(path.join(root, "__init__.py")):
                depth += 1
            else:
                root += ".py"
                if not path.isfile(root):
                    return None, None
        if i == len(imps) - 1:
            return root, depth
        else:
            if not path.isdir(root):
                return None, None
    return root

def follow_imp(root, imp, depth):
    while True:
        if root.endswith(".py"):
            mod, incs, excs = import_code(root, 0)
            return getattr(mod, imp), None
        else:
            n_imp = find_imp(root, imp, depth)
            if n_imp == False:
                return None, None
            elif n_imp is not None:
                imp = re.sub(r".*([^\.]+)", r"\1", n_imp)
                root, depth = resolve_imp(root, re.sub(r"(.*)[^\.]+", r"\1", n_imp).rstrip("."), depth)
                if root is None:
                    return None, None
            else:
                root = path.join(root, imp)
                if path.isfile(path.join(root, "__init__.py")):
                    depth += 1
                else:
                    root += ".py"
                    if not path.isfile(root):
                        return None, None
                return root, depth

def get_members(mod, tree):
    for obj in inspect.getmembers(mod):
        if not obj[0].startswith("_"):
            if inspect.isfunction(obj[1]):
                tree["funcs"].append(obj)
            elif inspect.isclass(obj[1]):
                if inspect.getmro(obj[1])[-2] == BaseException:
                    tree["excepts"].append(obj)
                else:
                    tree["classes"].append(obj)

def build_tree(root, depth=1, parent=""):
    mod, incs, excs = import_code(root, depth)
    tree = {}
    tree["name"] = parent + "." + path.basename(root) if parent else path.basename(root)
    tree["path"] = root
    tree["code"] = mod
    tree["funcs"] = []
    tree["classes"] = []
    tree["excepts"] = []
    tree["mods"] = []
    tree["packs"] = []
    
    get_members(mod, tree)
    
    for f in listdir(root):
        if path.splitext(f)[0] not in excs and not f.startswith("_"):
            if path.isfile(path.join(root, f, "__init__.py")):
                tree["packs"].append((f, build_tree(path.join(root, f), depth + 1, tree["name"])))
            elif f.endswith(".py") and path.isfile(path.join(root, f)):
                tree["mods"].append((path.splitext(f)[0], path.join(root, f)))
    
    for inc in incs:
        i_root, i_depth = resolve_imp(root, inc[0], depth)
        if i_root is not None:
            for imp in inc[1]:
                obj, ob_depth = follow_imp(i_root, imp[0], i_depth)
                if obj is not None:
                    name = imp[1]
                    if isinstance(obj, str):
                        if obj.endswith(".py"):
                            tree["mods"].append((name, obj))
                        else:
                            tree["packs"].append((name, build_tree(obj, ob_depth, tree["name"])))
                    elif inspect.isfunction(obj):
                        tree["funcs"].append((name, obj))
                    elif inspect.isclass(obj):
                        if inspect.getmro(obj)[-2] == BaseException:
                            tree["excepts"].append((name, obj))
                        else:
                            tree["classes"].append((name, obj))
    sort_key = lambda x: x[0]
    tree["funcs"].sort(key=sort_key)
    tree["classes"].sort(key=sort_key)
    tree["excepts"].sort(key=sort_key)
    tree["mods"].sort(key=sort_key)
    tree["packs"].sort(key=sort_key)
    return tree

def esc(string):
    #Escape Markdown
    string = re.sub("([{}])".format(re.escape(r"\`*_{}[]()#+-.!")), r"\\\1", string)
    #Escape HTML
    string = string.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return string

def process_doc_memb(lines, prop):
    while lines:
        line = lines.pop(0)
        if line.strip() == "":
            break
        else:
            if line.startswith("        "):
                prop[-1][1] += "\n" + line.strip()
            elif line.startswith("    "):
                prop.append(line.strip().split(": ", 1))

def get_docstr(obj):
    docstr = inspect.getdoc(obj)
    if docstr is None:
        return None, [], [], [], []
    
    new_lines = []
    attrs = []
    args = []
    returns = []
    raises = []
    lines = docstr.splitlines()
    while lines:
        line = lines.pop(0)
        if len(new_lines) == 0 or new_lines[-1] == "":
            if line == "Attributes:":
                process_doc_memb(lines, attrs)
            elif line == "Args:":
                process_doc_memb(lines, args)
            elif line == "Returns:":
                while lines:
                    line = lines.pop(0)
                    if line.strip() == "":
                        break
                    else:
                        returns.append(line)
            elif line == "Raises:":
                process_doc_memb(lines, raises)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
    return "\n".join(new_lines), attrs, args, returns, raises

def get_args(obj):
    sig = inspect.signature(obj)
    params = sig.parameters
    args = []
    has_key = False
    for param in params:
        p = params[param]
        if str(p.kind) == 'KEYWORD_ONLY':
            if (len(args) == 0 or not args[-1].startswith("\\*")) and not has_key:
                args.append("\\*")
                has_key = True
            args.append("")
        elif str(p.kind) == 'VAR_POSITIONAL':
            args.append("\\*")
        elif str(p.kind) == 'VAR_KEYWORD':
            args.append("\\*\\*")
        else:
            args.append("")
        
        args[-1] += p.name
        if p.default != inspect._empty:
            args[-1] += "=" + repr(p.default)
    return ", ".join(args)

def format_string(string, first="**", rest="*"):
    formatted = ""
    if re.search(r".+\(.+\)", string):
        split = string.split("(", 1)
        strings = re.split(r'([a-zA-Z0-9_\."]+)', split[0])
        for st in strings:
            if re.search(r'[a-zA-Z0-9_\."]+', st) and st != "or":
                formatted += "{1}{0}{1}".format(esc(st), first)
            else:
                formatted += esc(st)
        formatted += "\\("
        strings = re.split(r'([a-zA-Z0-9_\."]+)', split[1])
        for st in strings:
            if re.search(r'[a-zA-Z0-9_\."]+', st) and st != "or":
                formatted += "{1}{0}{1}".format(esc(st), rest)
            else:
                formatted += esc(st)
    else:
        strings = re.split(r'([a-zA-Z0-9_\."]+)', string)
        is_first = True
        for st in strings:
            if re.search(r'[a-zA-Z0-9_\."]+', st) and st != "or":
                if is_first:
                    formatted += "{1}{0}{1}".format(esc(st), first)
                    is_first = False
                else:
                    formatted += "{1}{0}{1}".format(esc(st), rest)
            else:
                formatted += esc(st)
    return formatted

def match_parenthesis(chars):
    string = ""
    count = 1
    while chars and count > 0:
        char = chars.pop(0)
        string += char
        if char == "(":
            count += 1
        elif char == ")":
            count -= 1
    return string

def wrap_return(string):
    string = format_string(string, rest="**")
    chars = list(string)
    split = []
    while chars:
        char = chars.pop(0)
        if char == "\\" and chars:
            char += chars.pop(0)
        if char == "\\(":
            split.append(char + match_parenthesis(chars))
        elif char == " ":
            pass
        else:
            split.append(char)
            while chars:
                char = chars.pop(0)
                if char == "(":
                    split[-1] += match_parenthesis(chars)
                elif char == " ":
                    break
                else:
                    split[-1] += char
    
    parts = ["<code>" + split.pop(0)]
    while split:
        part = split.pop(0)
        if part == "or":
            parts[-1] += "</code>"
            parts.append("<code>" + split.pop(0))
        else:
            parts[-1] += " " + part
    parts[-1] += "</code>"
    
    return " or ".join(parts)

def format_returns(returns, depth=0):
    ret = returns.pop(0).split(":", 1)
    formatted = ("    " * depth) + wrap_return(ret[0])
    if len(ret) == 2:
        formatted += ":" + esc(ret[1])
    formatted += "  "
    
    for ret in returns:
        formatted += "\n" + ("    " * depth)
        split = ret.split(": ", 1)
        if re.search(r"[\(\)\[\]\{\}]$", split[0]):
            parts = re.split(r"^( *)", split[0])
            if len(parts) == 3:
                indent = len(parts[1])
                text = parts[2]
            else:
                indent = 0
                text = parts[0]
            formatted += ("&nbsp;" * (indent - 4)) + "<code>"
            if re.search(r'^[a-zA-Z0-9_\."]+ ', text.strip()):
                formatted += format_string(text)
            else:
                formatted += format_string(text, "*")
            formatted += "</code>"
            if len(split) == 2:
                formatted += ": " + esc(split[1])
            formatted += "  "
        else:
            formatted += esc(": ".join(split).strip()) + "  "
    return formatted

def write_functions(funcs, parent, f, depth=0, prefix=False):
    missing_doc = []
    indent = "    " * depth
    first = True
    for func in funcs:
        if not first:
            f.write("\n---\n\n")
        first = False
        
        f.write('{}* <a id="function-{}-{}"></a>{}{}\\.**{}(**<i>{}</i>**)**  \n'.format(
            indent, parent, func[0], "*function* " * prefix, esc(parent), esc(func[0]), esc(get_args(func[1]))))
        doc, attrs, args, returns, raises = get_docstr(func[1])
        if doc is None:
            missing_doc.append(func[0])
        else:
            for line in doc.splitlines():
                if line == "":
                    f.write("\n")
                else:
                    f.write("{}    {}  \n".format(indent, esc(line)))
            f.write("\n")
        
        if len(args) > 0:
            f.write(indent + "    **Arguments:**\n")
            for arg in args:
                f.write("{}    * <code>{}</code>: {}\n".format(indent, format_string(arg[0]), esc(arg[1])))
            f.write("\n")
        
        if len(attrs) > 0:
            f.write(indent + "    **Attributes:**\n")
            for attr in attrs:
                f.write("{}    * <code>{}\\.{}</code>: {}\n".format(indent, esc(func[0]), format_string(attr[0]), esc(attr[1])))
            f.write("\n")
        
        if len(returns) > 0:
            f.write(indent + "    **Returns:**\n\n")
            f.write(format_returns(returns, depth + 1) + "\n")
            f.write("\n")
        
        if len(raises) > 0:
            f.write(indent + "    **Raises:**\n")
            for r in raises:
                f.write("{}    * <code>{}</code>: {}\n".format(indent, format_string(r[0]), esc(r[1])))
            f.write("\n")
    return missing_doc

def write_classes(classes, parent, f):
    missing_doc = []
    first = True
    for cls in classes:
        if not first:
            f.write("\n---\n\n")
        first = False
        
        f.write('* <a id="class-{}-{}"></a>*class* {}\\.**{}(**<i>{}</i>**)**  \n'.format(
            parent, cls[0], esc(parent), esc(cls[0]), esc(get_args(cls[1]))))
        doc, attrs, args = get_docstr(cls[1])[:3]
        if doc is None:
            missing_doc.append(cls[0])
        else:
            for line in doc.splitlines():
                if line == "":
                    f.write("\n")
                else:
                    f.write("    {}  \n".format(esc(line)))
            f.write("\n")
        
        if len(args) > 0:
            f.write("    **Arguments:**\n")
            for arg in args:
                f.write("    * <code>{}</code>: {}\n".format(format_string(arg[0]), esc(arg[1])))
            f.write("\n")
        
        if len(attrs) > 0:
            f.write("    **Attributes:**\n")
            for attr in attrs:
                f.write("    * <code>{}\\.{}</code>: {}\n".format(esc(cls[0]), format_string(attr[0]), esc(attr[1])))
            f.write("\n")
        
        funcs = [func for func in inspect.getmembers(cls[1], inspect.isfunction) if not func[0].startswith("_")]
        if len(funcs) > 0:
            f.write("    **Methods:**")
            write_functions(funcs, cls[0], f, 1)
    return missing_doc

def write_header(code, hierarchy, p_path, f, module=False):
    header = "#"
    if module:
        start = 2
        add = 0
    else:
        start = 1
        add = 1
    
    for i, level in enumerate(hierarchy, start=start):
        depth = len(hierarchy) - i
        header += "["
        if i > start:
            header += "\\."
        if depth == -1:
            header += "{}]({}.md)".format(esc(level), level)
        else:
            header += "{}]({}__init__.md)".format(esc(level), "../" * depth)
    header += "\n\n"
    f.write(header)
    
    if module:
        f.write("**Source code:** [{}]({}{})\n\n".format(esc(p_path + ".py"), "../" * (len(hierarchy) + add), p_path + ".py"))
    else:
        f.write("**Source code:** [{}/\\_\\_init\\_\\_\\.py]({}{}/__init__.py)\n\n".format(esc(p_path), "../" * (len(hierarchy) + add), p_path))
    
    doc, attrs = get_docstr(code)[:2]
    if doc is not None:
        for line in doc.splitlines():
            if line == "":
                f.write("\n")
            else:
                f.write("{}  \n".format(esc(line)))
        f.write("\n")
    return attrs, True if doc else False

def write_module(members, name, attrs, f):
    missing_doc = {
        "classes": [],
        "functions": [],
        "exceptions": []
        }
    
    if len(members["classes"]) > 0:
        f.write("####[Classes](#classes-1)\n")
        for cls in members["classes"]:
            f.write("* <code>{}\\.[**{}**](#class-{}-{})</code>\n".format(esc(name), esc(cls[0]), name, cls[0]))
        f.write("\n")
    
    if len(members["funcs"]) > 0:
        f.write("####[Functions](#functions-1)\n")
        for func in members["funcs"]:
            f.write("* <code>{}\\.[**{}**](#function-{}-{})</code>\n".format(esc(name), esc(func[0]), name, func[0]))
        f.write("\n")
    
    if len(attrs) > 0:
        f.write("####[Attributes](#attributes-1)\n")
        for attr in attrs:
            f.write("* <code>{}\\.[**{}**](#attribute-{}-{})</code>\n".format(
                esc(name), esc(attr[0].split("(")[0].strip()), name, attr[0].split("(")[0].strip()))
        f.write("\n")
    
    if len(members["excepts"]) > 0:
        f.write("####[Exceptions](#exceptions-1)\n")
        for exc in members["excepts"]:
            f.write("* <code>{}\\.[**{}**](#exception-{}-{})</code>\n".format(esc(name), esc(exc[0]), name, exc[0]))
        f.write("\n")
    
    #Build member documentation
    if len(members["classes"]) > 0:
        f.write("##Classes\n")
        missing_doc["classes"] = write_classes(members["classes"], name, f)
    
    if len(members["funcs"]) > 0:
        f.write("##Functions\n")
        missing_doc["functions"] = write_functions(members["funcs"], name, f, prefix=True)
    
    if len(attrs) > 0:
        f.write("##Attributes\n")
        first = True
        for attr in attrs:
            first = False
            
            f.write('* <a id="attribute-{}-{}"></a>*attribute* {}\\.{}: {}\n'.format(
                name, attr[0].split("(")[0].strip(), esc(name), format_string(attr[0]), esc(attr[1])))
        f.write("\n")
    
    if len(members["excepts"]) > 0:
        f.write("##Exceptions\n")
        first = True
        for exc in members["excepts"]:
            if not first:
                f.write("\n---\n\n")
            first = False
            
            f.write('* <a id="exception-{}-{}"></a>*exception* {}\\.**{}**  \n'.format(name, exc[0], esc(name), esc(exc[0])))
            doc = inspect.getdoc(exc[1])
            if doc is None:
                missing_doc["exceptions"].append(exc[0])
            else:
                for line in doc.splitlines():
                    if line == "":
                        f.write("\n")
                    else:
                        f.write("    {}  \n".format(esc(line)))
            f.write("\n")
    
    return missing_doc

def build_docs(tree, out):
    missing_doc = {
        "packages": [],
        "modules": [],
        "classes": [],
        "functions": [],
        "exceptions": []
        }
    p_name = tree["name"]
    p_path = path.normpath(tree["path"]).replace("\\", "/")
    hierarchy = p_name.split(".")
    name = hierarchy[-1]
    doc_path = path.join(out, *hierarchy)
    
    print("Writing package: {}".format(name))
    
    makedirs(doc_path)
    f = open(path.join(doc_path, "__init__.md"), 'w', encoding="utf-8")
    
    attrs, has_doc = write_header(tree["code"], hierarchy, p_path, f)
    
    if not has_doc:
        missing_doc["packages"] = [name]
    
    #Build index with links to members and to types (classes, functions...)
    if len(tree["packs"]) > 0 or len(tree["mods"]) > 0 or len(tree["funcs"]) > 0 or len(tree["classes"]) > 0 or len(tree["excepts"]) > 0 or len(attrs) > 0:
        f.write("##Index\n")
    
    if len(tree["packs"]) > 0:
        f.write("####Subpackages\n")
        for pack in tree["packs"]:
            f.write("* <code>{}\\.[**{}**]({}/__init__.md)</code>\n".format(esc(name), esc(pack[0]), pack[0]))
        f.write("\n")
    
    if len(tree["mods"]) > 0:
        f.write("####Modules\n")
        for mod in tree["mods"]:
            f.write("* <code>{}\\.[**{}**]({}.md)</code>\n".format(esc(name), esc(mod[0]), mod[0]))
        f.write("\n")
    
    mod_missing_doc = write_module(tree, name, attrs, f)
    for obj in mod_missing_doc:
        missing_doc[obj] = mod_missing_doc[obj]
    f.close()
    
    for mod in tree["mods"]:
        i_mod = import_code(mod[1], 0)[0]
        members = {
            "funcs": [],
            "classes": [],
            "excepts": []
            }
        get_members(i_mod, members)
        
        print("Writing module: {}".format(mod[0]))
        
        f = open(path.join(doc_path, mod[0] + ".md"), 'w', encoding="utf-8")
        attrs, has_doc = write_header(i_mod, hierarchy + [mod[0]], path.join(p_path, mod[0]), f, True)
        if not has_doc:
            missing_doc["modules"].append(mod[0])
        
        mod_missing_doc = write_module(members, mod[0], attrs, f)
        for obj in mod_missing_doc:
            missing_doc[obj].extend(mod_missing_doc[obj])
        f.close()
    
    for pack in tree["packs"]:
        pack_missing_doc = build_docs(pack[1], out)
        for obj in pack_missing_doc:
            missing_doc[obj].extend(pack_missing_doc[obj])
    
    return missing_doc

def build_index(tree, out):
    f = open(path.join(out, "index.md"), 'w', encoding="utf-8")
    f.write("#Index of {} package\n\n".format(tree["name"].split(".")[-1]))
    
    f.write("* *package* [**{}**]({})\n".format(tree["name"], path.join(tree["name"], "__init__.md")))
    
    def write_contents(tree, f, depth=1):
        for pack in tree["packs"]:
            f.write("{}* *package* [**{}**]({})\n".format("    " * depth, pack[0], path.join(*pack[1]["name"].split(".") + ["__init__.md"])))
            write_contents(pack[1], f, depth + 1)
        for mod in tree["mods"]:
            f.write("{}* *module* [**{}**]({})\n".format("    " * depth, mod[0], path.join(*tree["name"].split(".") + [mod[0] + ".md"])))
    
    write_contents(tree, f)

def print_usage():
    print("Usage: Py.md <input> <output>")
    print("    input may be a python file or package.")
    print("    output is the documentation directory.")

opts, args = getopt(sys.argv[1:], "h", ["help"])

for opt, arg in opts:
    if opt in ("-h", "--help"):
        print_usage()
        sys.exit()

if len(args) != 2:
    print_usage()
    sys.exit(2)

inp = args[0]
out = args[1]

if not path.isdir(out):
    print("Output directory does not exist.")
    sys.exit(1)

if path.isdir(inp):
    if path.isfile(path.join(inp, "__init__.py")):
        rmtree(out)
        makedirs(out)
        print()
        tree = build_tree(inp)
        missing_doc = build_docs(tree, out)
        build_index(tree, out)
        print()
        for obj, docs in missing_doc.items():
            if len(docs) > 0:
                print("{} {} are missing a docstring:".format(len(docs), obj))
                for doc in docs:
                    print(doc)
                print()
    else:
        print("Input directory is not a python package.")
        sys.exit(1)
