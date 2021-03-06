import re
from six import string_types
from collections import Counter
from sage.all import cached_function, ZZ, RR, GCD, ceil, RealField, ComplexField
from sage.rings.complex_number import ComplexNumber
from lmfdb.encoding import LmfdbRealLiteral
from dirichlet_conrey import DirichletGroup_conrey, DirichletCharacter_conrey

HEADER = "id|origin|primitive|conductor|central_character|self_dual|motivic_weight|Lhash|degree|order_of_vanishing|algebraic|z1|gamma_factors|trace_hash|root_angle".split("|")
TYPES = "bigint|text|boolean|numeric|text|boolean|smallint|text|smallint|smallint|boolean|numeric|jsonb|bigint|double precision".split("|")
OUTHEADER = "id|origin|primitive|conductor|central_character|self_dual|motivic_weight|Lhash|degree|order_of_vanishing|algebraic|z1|gamma_factors|trace_hash|root_angle|prelabel|analytic_conductor|mu_real|mu_imag|double_nu_real|double_nu_imag|bad_primes".split("|")
OUTTYPES = "bigint|text|boolean|numeric|text|boolean|smallint|text|smallint|smallint|boolean|numeric|jsonb|bigint|double precision|text|double precision|smallint[]|numeric[]|smallint[]|numeric[]|bigint[]".split("|")

CC_RE = re.compile(r'^(?=[iI.\d+-])([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?(?![iI.\d]))?\s*(?:([+-]?\s*(?:(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)?)?\s*\*?\s*[iI])?$')
class ComplexLiteral(ComplexNumber):
    def __init__(self, real, imag=None):
        def find_prec(s):
            if isinstance(s, string_types):
                # strip negatives and exponent
                s = s.replace("-","")
                if "e" in s:
                    s = s[:s.find("e")]
                return ceil(len(s) * 3.322)
            else:
                try:
                    return s.parent().precision()
                except Exception:
                    return 53
        if imag is None:
            # Process strings
            if isinstance(real, string_types):
                M = CC_RE.match(real)
                if M is None:
                    raise ValueError("'%s' not a valid complex number" % real)
                a, b = M.groups()
                # handle missing coefficient of i
                if b == '-':
                    b = '-1'
                elif b in ['+', '']:
                    b = '1'
                # The following is a good guess for the bit-precision,
                # but we use LmfdbRealLiterals to ensure that our number
                # prints the same as we got it.
                prec = max(find_prec(a), find_prec(b), 53)
                parent = ComplexField(prec)
                R = parent._real_field()
                self._real_literal = LmfdbRealLiteral(R, a)
                self._imag_literal = LmfdbRealLiteral(R, b)
            elif isinstance(real, LmfdbRealLiteral):
                parent = ComplexField(real.parent().precision())
                self._real_literal = real
                self._imag_literal = parent._real_field()(0)
            elif isintance(real, ComplexLiteral):
                parent = real.parent()
                self._real_literal = real._real_literal
                self._imag_literal = real._imag_literal
            else:
                raise TypeError("Object '%s' of type %s not valid input" % (real, type(real)))
        else:
            prec = max(find_prec(real), find_prec(imag), 53)
            R = RealField(prec)
            parent = ComplexField(prec)
            for x, xname in [(real, '_real_literal'), (imag, '_imag_literal')]:
                if isinstance(x, string_types):
                    x = LmfdbRealLiteral(R, x)
                if not isinstance(x, LmfdbRealLiteral):
                    raise TypeError("Object '%s' of type %s not valid input" % (x, type(x)))
                setattr(self, xname, x)
        ComplexNumber.__init__(self, self.real(), self.imag())

    def real(self):
        return self._real_literal

    def imag(self):
        return self._imag_literal

    def __repr__(self):
        s = ""
        if self.real():
            s = repr(self.real())
        if self.imag():
            y = self.imag()
            if s:
                if y < 0:
                    s += "-"
                    y = -y
                else:
                    s += "+"
            ystr = repr(y)
            s += ystr + "*I"
        if not s:
            s = repr(self.real())
        return s

def CCtuple(z):
    return (z.real(), z.imag().abs(), z.imag())

def spectral_str(x, conjugate=False):
    if conjugate:
        assert x <= 0
        x = -x
        res = "c"
    elif x < 0:
        x = -x
        res = "m"
    else:
        res = "p"
    if x == 0:
        res += "0"
    else:
        res += "%.2f" % x
    return res

def load(x, H, T):
    if T == "text":
        return x
    elif T == "boolean":
        return True if x == "t" else False
    elif T in ["bigint", "smallint"] or H == "conductor":
        return ZZ(x)
    elif T == "bigint[]":
        return [ZZ(a) for a in x[1:-1].split(",")]
    elif T == "double precision" or H == "z1":
        # Use LmfdbRealLiteral so that we can get the original string back
        return LmfdbRealLiteral(RR, x)
    elif H == "gamma_factors":
        return [[CompexLiteral(s) for s in piece[1:-1].split(",")] for piece in x[1:-1].replace(" ","").split("],[")]
    else:
        raise RuntimeError((x, H, T))

def save(x, H, T):
    if T == "text":
        return x
    elif T == "boolean":
        return "t" if x else "f"
    elif T in ["bigint", "smallint"] or H in ["conductor", "mu_imag", "double_nu_imag", "z1"]:
        return str(x)
    elif T in ["smallint[]", "numeric[]", "bigint[]"]:
        return "{%s}" % (",".join(repr(a) for a in x))
    elif H == "gamma_factors":
        return repr(x).replace(" ","")
    else:
        raise RuntimeError((x, H, T))

def process_line(line):
    L = {H: load(x, H, T) for (x, H, T) in zip(line.split("|"), HEADER, TYPES)}
    L["central_character"] = primitivize(L["central_character"])
    make_label(L) # also sets mus and nus
    L["analytic_conductor"] = analytic_conductor(L[)
    return "|".join(save(L[H], H, T) for (H, T) in zip(OUTHEADER, OUTTYPES))

@cached_function
def DirGroup(m):
    return DirichletGroup_conrey(m)

@cached_function
def primitivize(label):
    m, n = [ZZ(a) for a in label.split(".")]
    char = DirichletCharacter_conrey(DirGroup(m), n).primitive_character()
    return "%d.%d" % (char.modulus(), char.number())

def make_label(L):
    GR, GC = L['gamma_factors']
    analytic_normalization = L['motivic_weight']/2
    GR = [CDF(elt) + analytic_normalization for elt in GR]
    GC = [CDF(elt) + analytic_normalization for elt in GC]
    b, e = L['conductor'].perfect_power()
    if e == 1:
        conductor = b
    else:
        conductor = "{}e{}".format(b, e)
    beginning = "-".join(map(str, [L['degree'], conductor, L['central_character']]))

    GRcount = Counter(GR)
    GCcount = Counter(GC)
    # convert gamma_R to gamma_C
    zero = LmfdbRealLiteral(RR, '0')
    one = LmfdbRealLiteral(RR, '1')
    while GRcount[zero] > 0 and GRcount[one] > 0:
        GCcount[zero] += 1
        GRcount[zero] -= 1
        GRcount[one] -= 1
    GR = sum([[m]*c for m, c in GRcount.items()], [])
    GC = sum([[m]*c for m, c in GCcount.items()], [])
    assert L['degree'] == len(GR) + 2*len(GC)
    GR.sort(key=CCtuple)
    GC.sort(key=CCtuple)

    L["mu_imag"] = [elt.imag() for elt in GR]
    L["double_nu_imag"] = [2*elt.imag() for elt in GC]

    # deal with real parts
    GR_real = [elt.real() for elt in GR]
    GC_real = [elt.real() for elt in GC]
    L["mu_real"] = [x.round() for x in GR_real]
    L["double_nu_real"] = [(2*x).round() for x in GC_real]
    GRcount = Counter(GR_real)
    GCcount = Counter(GC_real)
    ge = GCD(GCD(list(GRcount.values())), GCD(list(GCcount.values())))
    if ge > 1:
        GR_real = sum(([k]*(v//ge) for k, v in GRcount.items()), [])
        GC_real = sum(([k]*(v//ge) for k, v in GCcount.items()), [])

    rs = ''.join(['r%d' % elt.real().round() for elt in GR_real])
    cs = ''.join(['c%d' % (elt.real()*2).round() for elt in GC_real])
    gammas = "-" + rs + cs
    if ge > 1:
        gammas += "e%d" % ge
    if L['algebraic']:
        end = "-0"
    else:
        end = "-"
        for G in [GR, GC]:
            for i, elt in enumerate(G):
                conjugate = False
                if elt.imag() <= 0 and i < len(G) - 1 and elt.conjugate() == G[i + 1]:
                    conjugate = True
                elif elt.imag() >= 0 and i > 0 and elt.conjugate() == G[i - 1]:
                    # we already listed this one as a conjugate
                    continue
                end += spectral_str(elt.imag(), conjugate=conjugate)
    L["prelabel"] = beginning + gammas + end

def analytic_conductor(L):
    
