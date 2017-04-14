import sys, os
import ast
import copy
import pp

python2 = sys.version[0] == "2"

def find_unparse_module():
    for path in sys.path:
        for dirpath, dirs, files in os.walk(path):
            for file in files:
                if file == "unparse.py":
                    sys.path.append(dirpath)
                    print("added ["+dirpath+"] to sys.path")
                    return

if python2:
    from StringIO import StringIO
else:
    from io import StringIO

find_unparse_module();

try:
    import unparse
except:
    if python2:
        import unparse2 as unparse
    else:
        import unparse3 as unparse

INIT = "__init__.py"

###########################################################################
#### Globals ##############################################################

mainModule = None
userInteraction = True


###########################################################################
#### TODO #################################################################

#TODO - add support for relative importing (PEP 328)
#     - for each file, save the module in which he came from
#     - for each submodule, save the module in which he came from

#TODO - use the inerited fields from other classes
#TODO - obfuscate keywords in function call and decleration!
#TODO - distinguish between class' static fields and instances field
#TODO - check the __all__ in python file (maybe add this to the analyzer)
#TODO - support globals
#TODO - mark the type of function arguments (seperate round for this)
#TODO - support attribute with 'ast.Call' inside

#TODO - support python2:
#     - replace type(x) with instanceof()
#     - in function definition handle all args as names !


###########################################################################
#### general utils ########################################################

def perror(msg):
    print(sys._getframe().f_code.co_name + ": " + msg)


###########################################################################
#### objects ##############################################################

class MaskedObj:

    def real(self):
        if type(self.name) is tuple:
            return self.name[0]
        return self.name

    def mask(self):
        return self.name[1]

    def findName(self, name):
        for field in self.fields():
            for obj in field:
                if obj.real() == name:
                    return obj
        return False

    def matchField(self, attrList, maskedAttrList):

        # list is empty => current object is the last one
        if not attrList:
            return (self, maskedAttrList)

        field = self.findName(attrList[0])

        if field:
            maskedAttrList.append(field.mask())
            return field.matchField(attrList[1:], maskedAttrList)

        return (False, maskedAttrList)

    def getAll(self):
        all = []
        for field in self.fields():
            all.extend(field)
        return all

class Module(MaskedObj):

    def __init__(self, mod_path):
        self.name = ""
        self.path = ""
        self.variables = []
        self.functions = []
        self.classes = []
        self.files = []
        self.modules = []

        self.path, self.name = os.path.split(mod_path)
        joiner = lambda x: os.path.join(mod_path, x)

        # next of os.walk will get only first level of the dir's tree
        _, folders, files = next(os.walk(mod_path))

        for folder in folders:
            # if its a dir which conteins __init__ file then its a submoudle, otherwise igonre it
            if os.path.exists(os.path.join(mod_path, folder, INIT)):
                self.modules.append(Module(joiner(folder)))

        for file in filter(lambda x: x.endswith(".py"), files):

            with open(joiner(file), "r") as f:
                tree = ast.parse(f.read())

            if file == INIT:
                self.variables, self.functions, self.classes = ast_analyze(tree)
            else:
                self.files.append(File(tree, file))

    def __str__(self):
        return "Module->" + self.real()

    def fields(self):
        return [self.modules, self.files, self.classes, self.variables, self.functions]

class File(MaskedObj):

    def __init__(self, file_tree, file_name):
        # keeping the full file name for printing it later on
        self.fname = file_name
        # name of the module this file represent
        self.name = self.fname.rsplit(".", 1)[0]
        # analayzing this file object
        self.variables, self.functions, self.classes = ast_analyze(file_tree)

    def __str__(self):
        return "File->" + self.real()
    
    def fields(self):
        return [self.variables, self.functions, self.classes]

class Class(MaskedObj):

    def __init__(self, node):
        self.name = node.name
        self.variables, self.functions, self.classes = ast_analyze(node, isClass=True)

        # save link to other classes for inheritens realations.
        self.motherClasses = []
        self.sonsClasses = []

    def __str__(self):
        return "Class->" + self.real()

    def fields(self):
        fromMothers = []
        for mother in self.motherClasses:
            fromMothers.extend(mother.fields())
        return [self.variables, self.functions, self.classes] + fromMothers

class Function(MaskedObj):

    def __init__(self, name):
        self.name = name
        
        # should be represented as list of Variables or dict of "name" and "object"goo
        self.args = {} # dictionary of function args as Variables objects

    def __str__(self):
        return "Function->" + self.real()

    def fields(self):
        return []

class Variable(MaskedObj):

    def __init__(self, name):
        self.name = name
        # define the object this variable is representing (only if its from inside the project)
        self.object = None  

    def __str__(self):
        return "Variable->" + self.real()

    def setObject(self, obj):
        self.object = obj

    def fields(self):
        return self.object.fields() if self.object else []

class Env(MaskedObj):

    def __init__(self, variables=[]):
        self.variables = variables

    def append(self, obj):
        for var in self.variables:
            if var.name == obj.name:
                self.variables.remove(var)
        self.variables.append(obj)

    def extend(self, objList):
        for obj in objList:
            self.append(obj)

    def fields(self):
        return [self.variables]

    def getCopy(self, ext=[]):
        return Env(self.variables[:] + ext[:])


###########################################################################
#### ast related functions ################################################

def ast_extract_vars(mnode, isClass=False, inFunc=False):

    # if in function then still looking for self.X for class variables.

    var_list = set()
    for node in ast.iter_child_nodes(mnode):

        if type(node) == ast.FunctionDef and isClass:
            var_list.update(ast_extract_vars(node, isClass, inFunc=True))

        elif type(node) == ast.Assign:
            for target in node.targets:

                if (type(target)==ast.Attribute) and (type(target.value)==ast.Name) and (target.value.id=="self"):
                    var_list.add(Variable(target.attr))

                elif type(target) == ast.Name and not inFunc: 
                    var_list.add(Variable(target.id))

        elif type(node) not in (ast.FunctionDef, ast.ClassDef):
            var_list.update(ast_extract_vars(node, isClass, inFunc))

    return var_list

def ast_analyze(tree, isClass=False):

    # finds all tree vars
    tree_vars = list(ast_extract_vars(tree, isClass=isClass))

    # find functions and classes:
    tree_fuctions = []
    tree_classes = []

    for node in ast.iter_child_nodes(tree):

        if type(node) == ast.FunctionDef:
            tree_fuctions.append(Function(node.name))

        elif type(node) == ast.ClassDef:
            tree_classes.append(Class(node))

    if "__init__" in tree_fuctions:
        tree_fuctions.remove("__init__")

    return (tree_vars, tree_fuctions, tree_classes)

def pp_module(obj, level=0):
    tab = "\t"*level

    print("%s name: %s" % (tab, obj.name))    
    print("%s variables: \n%s%s" % (tab, tab+"\t", str(obj.variables)))
    print("%s functions: \n%s%s" % (tab, tab+"\t", str(obj.functions)))

    if hasattr(obj, 'classes'):
        for clss in obj.classes:
            print("%s class:" % tab)
            pp_module(clss, level+1)

    if hasattr(obj, 'files'):
        for file in obj.files:
            print("%s file:" % tab)
            pp_module(file, level+1)

    if hasattr(obj, 'modules'):
        for mod in obj.modules:
            print("%s module:" % tab)
            pp_module(mod, level+1)

def attrToList(obj):

    if type(obj) == str:
        return [obj]

    if type(obj) == ast.Name:
        return [obj.id]

    if type(obj) == ast.Attribute:
        return attrToList(obj.value) + attrToList(obj.attr)

    # encounter unsupported type
    raise Exception("match: encounter unsupported type")

def updateAttrFromList(obj, attrList):

    if type(obj) == ast.Name:
        obj.id = attrList.pop()

    if type(obj) == ast.Attribute:
        obj.attr = attrList.pop()
        updateAttrFromList(obj.value, attrList)


###########################################################################
#### mask related functions ###############################################

counter = 1
maskBank = {}

def mask_gen(name):
    global counter, maskBank

    if name in ("__init__", "self"):
        return (name, name)

    # checking wether this name has already been masked
    mask = maskBank.get(name)
    if mask:
        return (name, mask)

    # if this name has never been masked, then will create new mask for it
    mask = bin(counter)
    mask = mask[2:]
    mask = mask.zfill(20)
    mask = "X" + mask

    # storing name in mask bank for later use
    maskBank[name] = mask

    counter = counter +1
    return (name, mask)

def mask_module(obj):
    obj.name = mask_gen(obj.name)
    for field in obj.fields():
        list(map(mask_module, field))
        # map(mask_module, field)


###########################################################################
#### obfuscation handlers #################################################

def assign_user_interaction(node, env):
    global userInteraction

    if not userInteraction:
        return

    print("** found assaign with unknown type:")
    print("** -> " + astunparse.unparse(node))
    print("** (s:kip) (c:ancel) (i:mport) (t:ype) = [i import sys] or [t me.Object()]")
    usr = input().split(None, 1)

    if usr[0] is "s":
        return

    if usr[0] is "c":
        userInteraction = False
        return

    if usr[0] is "i":
        try:
            imp = ast.parse(usr[1])
            imp = imp.body[0]
            assert type(imp) in (ast.Import, ast.ImportFrom)
            env = env.getCopy()
            obfuscate_obj(imp, env)

        except:
            print("please enter import statment")

    if usr[0] is "t":
        try:
            obj = ast.parse(usr[1])
            obj = obj.body[0]
            assert type(obj) in (ast.Call, ast.Name, ast.Attribute)
            return obfuscate_obj(obj, env)[0]
        except:
            print("please enter a valid expression")

    return assign_user_interaction(node, env)

def handle_import_from(node, env):
    
    attrList = node.module.split(".")
    module, maskedAtrrList = mainModule.matchField(attrList, [])

    if not module: 
        return

    node.module = ".".join(maskedAtrrList)

    if (len(node.names)==1) and (node.names[0].name == "*"):
        env.extend(module.getAll())
    else:
        handle_import(node, module, env)

def handle_import(node, env):

    #TODO - check also in main_module (maybe save it as global)

    for alias in node.names:
        attrList = alias.name.split(".")
        val, maskedAtrrList = mainModule.matchField(attrList, [])

        if not val:
            continue

        #TODO - maybe change this to variable with type of 'val'
        if alias.asname:
            val = copy.copy(val)
            val.name = mask_gen(alias.asname)
            alias.asname = val.mask()

        env.append(val)
        alias.name = ".".join(maskedAtrrList)

def handle_assign(node, env):

    #TODO - hanlde tuple 2 tuple assign with diffarent types

    # if its name or attribute then its a one var list
    # in case of tuple or list, will take the fist type only
    value = obfuscate_obj(node.value, env)

    if len(value) > 0:
        value = value[0]

    if type(value) is Class:
        pass

    if type(value) is Variable:
        value = value.object

    for target in node.targets: 

        names = target.elts if (type(target) in (ast.Tuple, ast.List)) else [target]

        for name in names:
            if type(name) == ast.Name:
                print("@@@@ " + target.id)
                newVar = Variable(mask_gen(target.id))
                env.append(newVar)

        objs = obfuscate_obj(target, env)

        for obj in objs:
            if type(obj) == Variable:
                obj.object = value

def handle_call(node, env):

    # get all other childs and remove the func since it is evaluated seperatly
    child_nodes = list(ast.iter_child_nodes(node))
    child_nodes.remove(node.func)

    for child in child_nodes:
        obfuscate_obj(child, env)

    # evaluate func seperatl:y so it can be examined later
    func = obfuscate_obj(node.func, env)

    if func:
        func = func[0]

        # if this function belongs to the masked module then the keywords should also get their mask
        for kw in node.keywords:
            real, mask = mask_gen(kw.arg)
            kw.arg = mask

        # if the type is class then this call is actually constractor call
        if type(func) == Class:
            return func

    return None

def handle_function_def(func, env):

    funcObj = env.findName(func.name)
    assert type(funcObj) is Function

    env.extend(funcObj.getAll())

    func.name = funcObj.mask()

    obfuscate_childs(func, env)

def handle_lambda_def(node, env):
    pass

def handle_class_def(cls, env):

    clsObj = env.findName(cls.name)
    assert type(clsObj) is Class

    # self var has no mask, so mask() and real() should return same name
    selfVar = Variable(mask_gen("self"))
    selfVar.setObject(clsObj)
    env.extend(clsObj.getAll())
    env.append(selfVar)

    cls.name = clsObj.mask()
    obfuscate_childs(cls, env)

def handle_name_attribute(node, env):
    
    attrList = attrToList(node)

    val, maskedAtrrList = env.matchField(attrList, [])

    if len(maskedAtrrList) < 1:
        perror("didnt find [" + ".".join(attrList) + "] in current module")
        return None

    if len(attrList) != len(maskedAtrrList):
        maskedAtrrList += attrList[len(maskedAtrrList):]

    updateAttrFromList(node, maskedAtrrList)

    return val

def handle_arg(arg, env):

    if arg.arg == "self":
        return

    newVar = Variable(mask_gen(arg.arg))
    env.append(newVar)
    arg.arg = newVar.mask()

###########################################################################
#### variables types logics ###############################################

def typify_class_def(cls, env):

    clsObj = env.findName(cls.name)
    assert type(clsObj) is Class

    # self var has no mask, so mask() and real() should return same name
    selfVar = Variable(mask_gen("self"))
    selfVar.setObject(clsObj)
    env.extend(clsObj.getAll())
    env.append(selfVar)

    changed = False

    for base in cls.bases:

        baseObj = handle_name_attribute(base, env)

        if baseObj:

            assert type(clsObj) is Class

            if baseObj not in clsObj.motherClasses:
                clsObj.motherClasses.append(baseObj)
                changed = True

            if clsObj not in baseObj.sonsClasses:
                baseObj.sonsClasses.append(clsObj)
                changed = True


    classify_childs(cls, env)

    return changed

def typify_obj(node, env):

    # print("$$$ -> ", end=""); pp.parseprint(node)

    retVal = []

    if type(node) == ast.Import:
        handle_import(node, env)

    elif type(node) == ast.ImportFrom:
        handle_import_from(node, env)   
    
    # require copy of current env ######
    elif type(node) == ast.ClassDef:
        val = classify_class_def(node, env.getCopy())
        retVal.append(val)
    # ##################################

    else:
        val = classify_childs(node, env)
        retVal.append(val)

    return any(retVal)

def typify_childs(tree, env):

    retVal = []

    for node in ast.iter_child_nodes(tree):
        val = classify_obj(node, env)
        retVal.append(val)

    return any(retVal)

def typify_file(realPath, file):

    with open(realPath, "r") as realFile:
        tree = ast.parse(realFile.read())

    return classify_childs(tree, Env(file.getAll()))

def typify(mod):

    retVal = []

    realPath = os.path.join(mod.path, mod.real())

    for file in mod.files:
        fileRealPath = os.path.join(realPath, file.real() + ".py")
        val = classify_file(fileRealPath, file)
        retVal.append(val)

    # if this is a submodule then it will have INIT file
    # need to create INIT file without mask his name, only the content  

    initRealPath = os.path.join(realPath, INIT)

    if os.path.exists(initRealPath):
        val = classify_file(initRealPath, mod)
        retVal.append(val)

    for module in mod.modules:
        val = classify(module)
        retVal.append(val)

    # TODO - maybe there is no need for recursion here
    if any(retVal):
        classify(mod)


###########################################################################
#### class inheritence logics #############################################

def classify_class_def(cls, env):

    clsObj = env.findName(cls.name)
    assert type(clsObj) is Class

    # self var has no mask, so mask() and real() should return same name
    selfVar = Variable(mask_gen("self"))
    selfVar.setObject(clsObj)
    env.extend(clsObj.getAll())
    env.append(selfVar)

    changed = False

    for base in cls.bases:

        baseObj = handle_name_attribute(base, env)

        if baseObj:

            assert type(clsObj) is Class

            if baseObj not in clsObj.motherClasses:
                clsObj.motherClasses.append(baseObj)
                changed = True

            if clsObj not in baseObj.sonsClasses:
                baseObj.sonsClasses.append(clsObj)
                changed = True


    classify_childs(cls, env)

    return changed

def classify_obj(node, env):

    # print("$$$ -> ", end=""); pp.parseprint(node)

    retVal = []

    if type(node) == ast.Import:
        handle_import(node, env)

    elif type(node) == ast.ImportFrom:
        handle_import_from(node, env)   
    
    # require copy of current env ######
    elif type(node) == ast.ClassDef:
        val = classify_class_def(node, env.getCopy())
        retVal.append(val)
    # ##################################

    else:
        val = classify_childs(node, env)
        retVal.append(val)

    return any(retVal)

def classify_childs(tree, env):

    retVal = []

    for node in ast.iter_child_nodes(tree):
        val = classify_obj(node, env)
        retVal.append(val)

    return any(retVal)

def classify_file(realPath, file):

    with open(realPath, "r") as realFile:
        tree = ast.parse(realFile.read())

    return classify_childs(tree, Env(file.getAll()))

def classify(mod):

    retVal = []

    realPath = os.path.join(mod.path, mod.real())

    for file in mod.files:
        fileRealPath = os.path.join(realPath, file.real() + ".py")
        val = classify_file(fileRealPath, file)
        retVal.append(val)

    # if this is a submodule then it will have INIT file
    # need to create INIT file without mask his name, only the content  

    initRealPath = os.path.join(realPath, INIT)

    if os.path.exists(initRealPath):
        val = classify_file(initRealPath, mod)
        retVal.append(val)

    for module in mod.modules:
        val = classify(module)
        retVal.append(val)

    # TODO - maybe there is no need for recursion here
    if any(retVal):
        classify(mod)

###########################################################################
#### obfuscation main logics ##############################################

def obfuscate_obj(node, env):

    # print("$$$ -> ", end=""); pp.parseprint(node)

    retVal = []

    if type(node) in (ast.Name, ast.Attribute):
        val = handle_name_attribute(node, env)
        retVal.append(val)

    elif type(node) == ast.Call:
        val = handle_call(node, env)
        retVal.append(val)

    elif type(node) == ast.Import:
        handle_import(node, env)

    elif type(node) == ast.ImportFrom:
        handle_import_from(node, env)   
    
    # require copy of current env ######

    elif type(node) == ast.FunctionDef:
        handle_function_def(node, env.getCopy())
        
    elif type(node) == ast.Lambda:
        handle_lambda_def(node, env.getCopy())

    elif type(node) == ast.ClassDef:
        handle_class_def(node, env.getCopy())

    # ##################################

    elif type(node) == ast.Assign:
        handle_assign(node, env)

    elif type(node) in (ast.List, ast.Tuple):
        val = obfuscate_childs(node, env)
        retVal.extend(val)

    elif type(node) == ast.Starred:
        val = obfuscate_obj(node.value, env)
        retVal.extend(val)

    elif type(node) == ast.Subscript:
        obfuscate_obj(node.slice)
        val = obfuscate_obj(node.value, env)
        retVal.extend(val)

    elif type(node) == ast.arg:
        handle_arg(node, env)

    # Keyword, Global
    else:
        obfuscate_childs(node, env)

    return list(filter(None, retVal))

def obfuscate_childs(tree, env):

    retVal = []

    for node in ast.iter_child_nodes(tree):
        val = obfuscate_obj(node, env)
        retVal.extend(val)

    return retVal

def obfuscate_file(realPath, maskedPath, file):

    with open(realPath, "r") as realFile:
        tree = ast.parse(realFile.read())

    obfuscate_childs(tree, Env(file.getAll()))

    sfile = StringIO()
    unparse.Unparser(tree, sfile)

    with open(maskedPath, "w+") as maskedFile:
        maskedFile.write(sfile.getvalue())

    sfile.close()

def obfuscate(mod, masked_path):

    realPath = os.path.join(mod.path, mod.real())
    maskedPath = os.path.join(masked_path, mod.mask())

    if python2:
        try:
            os.makedirs(maskedPath)
        except:
            pass
    else:
        os.makedirs(maskedPath, exist_ok=True)

    for file in mod.files:
        fileRealPath = os.path.join(realPath, file.real() + ".py")
        fileMaskedPath = os.path.join(maskedPath, file.mask() + ".py")
        obfuscate_file(fileRealPath, fileMaskedPath, file)

    # if this is a submodule then it will have INIT file
    # need to create INIT file without mask his name, only the content  

    initRealPath = os.path.join(realPath, INIT)
    initMaskedPath = os.path.join(maskedPath, INIT)

    if os.path.exists(initRealPath):
        obfuscate_file(initRealPath, initMaskedPath, mod)

    for module in mod.modules:
        obfuscate(module, maskedPath)


###########################################################################
#### main #################################################################

def main():

    global mainModule

    if len(sys.argv) < 2:
        print("please specify project folder")
        exit(1)

    project_path = sys.argv[1]

    # verify path is obsulute 
    if not project_path.startswith("/") and project_path.find(":") < 0:
        project_path = os.path.join(os.getcwd(), project_path)

    # verify path does exists
    if not os.path.exists(project_path):
        print("path does not exists: %s" % project_path)
        exit(1)

    mainModule = Module(project_path)

    mask_module(mainModule)

    classify(mainModule)

    obfuscate(mainModule, mainModule.path)

if __name__ == "__main__":
    main()
