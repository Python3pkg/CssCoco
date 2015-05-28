import os
import json
import coco.syntax as grammar
import coco.ast.ast as cocoast
import coco.analysis as analysis
import src.parser as parser
import src.parse_tree as ast
import src.conventions as matching
import src.sequences as seqs
import src.descriptors as desc
import coco.ast.markers as markers

def get_css_parse_tree():
    filename = os.path.join('samples', 'tiny.css')
    file = open(filename)
    css = file.read()
    result = parser.Parser.parse_css(css)
    try:
        l = json.loads(result.decode('utf-8'))
    except ValueError:
        return None, '-----\nPlease check the validity of the css block!\n-----'
    tr = parser.SExprTransformer.transform(l)
    a = ast.ParseTreeBuilder.build(tr)
    print(a.pretty_print())
    return a, ''


class Expr(object):
    pass


class ApiExpr(Expr):
    def __init__(self, selector, method_list):
        self.selector = self
        self.method_list = method_list


class NotExpr(Expr):
    def __init__(self, operand_expr):
        self.operand_expr = operand_expr


class BinaryExpr(Expr):
    def __init__(self, left_expr, right_expr):
        self.left_expr = left_expr
        self.right_expr = right_expr


class AndExpr(BinaryExpr):
    pass


class EqualsExpr(BinaryExpr):
    pass


class InExpr(Expr):
    def __init__(self, expr, string_list):
        self.expr = expr
        self.string_list = string_list


class NotInExpr(InExpr):
    pass


class MatchExpr(Expr):
    def __init__(self, expr, regex):
        self.expr = expr
        self.regex = regex


class AstBuilder(object):

    def build_sheet(self, tree):
        assert tree.head == 'start'
        result = []
        for r in tree.tail:
            convention = self.build_rule(r)
            result.append(convention)
        return result

    def build_rule(self, tree):
        assert tree.head == 'rule'
        result = []
        for rule in tree.tail:
            if self.is_if_rule(rule):
                result.append(self.build_if_rule(rule))
            else:
                pass
        return result

    def is_if_rule(self, tree):
        return tree.head == 'if_rule'

    def build_if_rule(self, tree):
        markers = self.build_selector(tree.tail[1])
        if self.contains_where_clause(tree):
            filter_expr = self.dispatch_requirement(tree.tail[3])
            req_expr = self.dispatch_requirement(tree.tail[5])
            return None
        expr = self.dispatch_requirement(tree.tail[3])
        return None

    def contains_where_clause(self, tree):
        return tree.tail[2] == 'where'

    def dispatch_requirement(self, tree):
        if len(tree.tail) == 1 and tree.head == 'req_expr':
            return self.dispatch_requirement(tree.tail[0])
        if tree.head == 'req_atom':
            return self.build_atom_expr(tree)

        if len(tree.tail) == 2:
            if tree.tail[0] == 'not':
                return self.build_not_expr(tree)

        elif len(tree.tail) == 3:
            if tree.tail[0] == '(' and tree.tail[2] == ')':
                return self.dispatch_requirement(tree.tail[1])
            if tree.tail[1] == 'match':
                return self.build_match_expr(tree)
            if tree.tail[1] == '=':
                return self.build_equal_expr(tree)
            if tree.tail[1] == 'in':
                return self.build_in_expr(tree)
            if tree.tail[1] == 'and':
                return self.build_and_expr(tree)
        elif len(tree.tail) == 4:
            if tree.tail[1] == 'not' and tree.tail[2] == 'in':
                return self.build_not_in_expr(tree)
        raise NotImplementedError('What expr is this?!')

    def build_atom_expr(self, tree):
        marker = self._build_marker_two(tree.tail[0])
        methods = []
        for i in range(2, len(tree.tail), 2):
            methods.append(tree.tail[i])
        return ApiExpr(marker, methods)

    def build_not_expr(self, tree):
        operand_expr = self.dispatch_requirement(tree.tail[1])
        return NotExpr(operand_expr)

    def build_match_expr(self, tree):
        expr = self.dispatch_requirement(tree.tail[0])
        regex = tree.tail[2]
        return MatchExpr(expr, regex)

    def build_equal_expr(self, tree):
        left = self.dispatch_requirement(tree.tail[0])
        right = self.dispatch_requirement(tree.tail[2])
        return EqualsExpr(left, right)

    def build_in_expr(self, tree):
        expr = self.dispatch_requirement(tree.tail[0])
        list_ = []
        for i in range(1, len(tree.tail[2].tail), 2):
            list_.append(tree.tail[2].tail[i])
        return InExpr(expr, list_)

    def build_not_in_expr(self, tree):
        expr = self.dispatch_requirement(tree.tail[0])
        list_ = tree.tail[2]
        return NotInExpr(expr, list_)

    def build_and_expr(self, tree):
        left = self.dispatch_requirement(tree.tail[0])
        right = self.dispatch_requirement(tree.tail[2])
        return AndExpr(left, right)

    def build_selector(self, tree):
        res = []
        self._build_selector_inner(tree, res)
        return res

    def _build_selector_inner(self, tree, res):
        left = self._build_marker_two(tree.tail[0])
        res.append(left)
        if len(tree.tail) < 2:
            return

        if tree.tail[2].head == 'selector':
            self._build_selector_inner(tree.tail[2], res)
        else:
            right = self._build_marker_two(tree.tail[0])
            res.append(right)

    def _build_marker_two(self, ply_node):
        name = ply_node.select('name > *')[0]
        if name == 'rule':
            return markers.RuleMarker()
        if name == 'declaration':
            return markers.DeclarationMarker()
        if name == 'selector':
            return markers.SelectorMarker()
        if name == 'block':
            return markers.BlockMarker()
        if self._is_string(name):
            return markers.SymbolMarker(name[1:-1])
        if name == 'property':
            return markers.PropertyMarker()
        if name == 'value':
            return markers.ValueMarker()
        if name == 'eof':
            return markers.EofMarker()
        if name == 'comment':
            return markers.CommentMarker()
        if name == 'csv-comma':
            return markers.CsvCommaMarker()
        if name == 'selector-comma':
            return markers.SelectorCommaMarker()

        repetitions = -1
        if name == 'whitespace':
            return markers.WhitespaceMarker(repetitions)
        if name == 'space':
            return markers.SpaceMarker(repetitions)
        if name == 'newline':
            return markers.NewlineMarker(repetitions)
        if name == 'tab':
            return markers.TabMarker(repetitions)

        raise NotImplementedError('Other css marker are not implemented yet')

    def _is_string(self, str):
        return len(str) > 1 and str[0] == '"' and str[-1] == '"'


def get_coco_ast():
    coco_filename = os.path.join('samples', 'one.coco')
    coco_file = open(coco_filename)
    cs = coco_file.read()

    res = grammar.Parser.parse(cs)
    # aha = AstBuilder().build_sheet(res)
    # tree = cocoast.AstBuilder.build(res)
    return None




css_tree, error = get_css_parse_tree()
print(error)
if not error:
    coco_ast = get_coco_ast()
    # map = analysis.Evaluator.evaluate(coco_ast)

    # print(map.find_violations(css_tree))

pattern = seqs.ChildPattern(desc.SimpleDescriptor(type_='block'), desc.SimpleDescriptor(type_='declaration'))
for n in seqs.TreeWalker.find_parent_child_pattern(css_tree, pattern):
    pass


