import sys
from antlr4 import *
from Grammar.OWScriptLexer import OWScriptLexer
from Grammar.OWScriptParser import OWScriptParser
from Grammar.OWScriptVisitor import OWScriptVisitor
 
def main(argv):
    input_stream = FileStream(argv[1])
    lexer = OWScriptLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = OWScriptParser(stream)
    visitor = OWScriptVisitor()
    tree = parser.script()
    output = visitor.visit(tree)
    print(output)
 
if __name__ == '__main__':
    main(sys.argv)