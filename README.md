# py-namer
python camouflager, rename all your project's names (variables, function, modules, files, etc)  
using [astpp](http://alexleone.blogspot.co.uk/2010/01/python-ast-pretty-printer.html) as pp.py (thanks to Alex Leone)

## Motivation
Python is interpreter language. As such, it is really hard to compile it, and obfuscate code logic. Yet, sometimes there is a such need.  
Using Cython(http://cython.org) project will compile it to C code, But since in python everything is an Object, even function's local variables have thier name in a string somewhere and therefore it's very easy to de-compile or at least understand the basic of the code logic by taking a look at the compiled code strings.  
This is where py-namer comes handy, it will rename everything in a given project folder: files, import statments, classes, functions and variables. 

## How its work
The main chalange here is to distinguish between object beloning the the current project being renamed and other objects that has been imported to the project from python library or other 3rd party modules.  
So for example if i have a class named 'myclass' with function called '__str__' i still want '__str__' to be renamed but only if a variable is from type 'myclass' and not all other object that probably also have function called '__str__'  
py-namer evaulate the Abstract Syntax Tree top to bottom with 4 main stages:

###### stage1: public names tree
In the first stage a general tree of the entire project is been build. This tree contains all the global names that can be used in other places. For example if the file a.py is importing b.py the tree should know which public names can be used from 'b' module so the new names of 'b' module will be used inside 'a'  

###### stage2: class inheritance verification
In this stage fixed point algoritem is iterating until every class knows the classes its inherit from so the new names of public variables from higher classes could be used in lower classes instances usage.

###### stage3: types verification
**This stage is still in prograss**.  
The porpuse of this stage is to make sure that each variable (either function args or local vars) that have a type from the current project is marked as such so in case there is a use in the object attributes, the currect new names will be usaed.

###### stage4: renaming
After collecting all the needed information, the renaming can start. Generating binary representaion for each renamed variable. Everything in the porject that can be renamed, will be. Complete folder structure, files, modules, classes and so on...

## Usage: 
    python pynamer.py project-folder  
result: new folder named X0000...0001 with project content.


#### before: 
![](https://github.com/dorki/py-namer/blob/master/pics/original.png)
#### after:
![](https://github.com/dorki/py-namer/blob/master/pics/named.png)

