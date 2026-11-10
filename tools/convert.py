#!/usr/bin/env python3
"""PPTX -> absolutely positioned HTML (1920x1080 stage).

Every top-level shape becomes its own element so it can animate on entry.
Usage: convert.py <unzipped-pptx-dir> <out-deck-dir> <deck-id> <title>
"""
import sys, os, re, json, math, shutil, html, colorsys
from lxml import etree

NS = {
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'a14': 'http://schemas.microsoft.com/office/drawing/2010/main',
    'asvg': 'http://schemas.microsoft.com/office/drawing/2016/SVG/main',
    'mc': 'http://schemas.openxmlformats.org/markup-compatibility/2006',
    'rel': 'http://schemas.openxmlformats.org/package/2006/relationships',
}
A = '{%s}' % NS['a']; P = '{%s}' % NS['p']; R = '{%s}' % NS['r']
EMU_PX = 12192000 / 1920.0          # 6350 EMU per px
PT_PX = 2.0                          # 1pt = 2px on a 1920 stage (13.333in * 144)


def px(v):
    return float(v) / EMU_PX


def fmt(v):
    s = ('%.2f' % v).rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def esc(s):
    return html.escape(s, quote=True)


def q(el, path):
    return el.find(path, NS) if el is not None else None


def qa(el, path):
    return el.findall(path, NS) if el is not None else []


# --------------------------------------------------------------------------- package
class Part:
    def __init__(self, pkg, path):
        self.pkg, self.path = pkg, path
        self.xml = etree.parse(os.path.join(pkg.root, path)).getroot()
        d, b = os.path.split(path)
        relp = os.path.join(pkg.root, d, '_rels', b + '.rels')
        self.rels = {}
        if os.path.exists(relp):
            for r in etree.parse(relp).getroot():
                tgt = r.get('Target')
                if r.get('TargetMode') != 'External':
                    tgt = os.path.normpath(os.path.join(d, tgt))
                self.rels[r.get('Id')] = (r.get('Type').rsplit('/', 1)[-1], tgt)

    def rel(self, rid):
        return self.rels.get(rid, (None, None))[1]

    def rel_of_type(self, t):
        for k, (tt, tgt) in self.rels.items():
            if tt == t:
                return tgt


class Pkg:
    def __init__(self, root):
        self.root = root
        self.pres = Part(self, 'ppt/presentation.xml')
        theme = None
        self.slides = []
        for sid in qa(self.pres.xml, 'p:sldIdLst/p:sldId'):
            self.slides.append(self.pres.rel(sid.get(R + 'id')))
        m0 = self.pres.rel_of_type('slideMaster')
        self.master = Part(self, m0)
        self.theme = Part(self, self.master.rel_of_type('theme'))
        cs = q(self.theme.xml, './/a:clrScheme')
        self.scheme = {}
        for c in cs:
            tag = etree.QName(c).localname
            v = c[0].get('val') if c[0].get('lastClr') is None else c[0].get('lastClr')
            self.scheme[tag] = v
        cm = q(self.master.xml, 'p:clrMap')
        self.clrmap = dict(cm.attrib)
        fs = q(self.theme.xml, './/a:fontScheme')
        self.major = q(fs, 'a:majorFont/a:latin').get('typeface')
        self.minor = q(fs, 'a:minorFont/a:latin').get('typeface')


# --------------------------------------------------------------------------- colour
def hex2rgb(h):
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


class Color:
    def __init__(self, rgb, a=1.0):
        self.rgb, self.a = rgb, a

    def css(self, extra_alpha=1.0):
        r, g, b = (max(0, min(255, round(c * 255))) for c in self.rgb)
        a = self.a * extra_alpha
        if a >= 0.999:
            return '#%02x%02x%02x' % (r, g, b)
        return 'rgba(%d,%d,%d,%s)' % (r, g, b, fmt(a) if a >= 0.01 else '%.3f' % a)


def parse_color(pkg, el, phclr=None):
    """el = element containing a colour child (srgbClr/schemeClr/...)."""
    if el is None:
        return None
    c = None
    for ch in el:
        ln = etree.QName(ch).localname
        if ln in ('srgbClr', 'schemeClr', 'prstClr', 'sysClr', 'scrgbClr'):
            c = ch
            break
    if c is None:
        return None
    ln = etree.QName(c).localname
    if ln == 'srgbClr':
        rgb = hex2rgb(c.get('val'))
    elif ln == 'sysClr':
        rgb = hex2rgb(c.get('lastClr') or '000000')
    elif ln == 'prstClr':
        rgb = hex2rgb({'black': '000000', 'white': 'FFFFFF'}.get(c.get('val'), '000000'))
    elif ln == 'schemeClr':
        v = c.get('val')
        if v == 'phClr' and phclr is not None:
            rgb = phclr.rgb
        else:
            v = pkg.clrmap.get(v, v)
            rgb = hex2rgb(pkg.scheme.get(v, '000000'))
    else:
        rgb = (0, 0, 0)
    a = 1.0
    h, l, s = colorsys.rgb_to_hls(*rgb)
    rgb = list(rgb)
    for m in c:
        mn = etree.QName(m).localname
        val = int(m.get('val', '0')) / 100000.0
        if mn == 'alpha':
            a = val
        elif mn == 'alphaMod':
            a *= val
        elif mn in ('lumMod', 'lumOff', 'satMod'):
            h, l, s = colorsys.rgb_to_hls(*rgb)
            if mn == 'lumMod':
                l *= val
            elif mn == 'lumOff':
                l += val
            else:
                s *= val
            rgb = list(colorsys.hls_to_rgb(h, max(0, min(1, l)), max(0, min(1, s))))
        elif mn == 'shade':
            rgb = [x * val for x in rgb]
        elif mn == 'tint':
            rgb = [x + (1 - x) * (1 - val) for x in rgb]
    return Color(tuple(rgb), a)


# --------------------------------------------------------------------------- fills
class Defs:
    def __init__(self):
        self.n = 0

    def id(self, p='g'):
        self.n += 1
        return '%s%d' % (p, self.n)


def grad_svg(pkg, gf, w, h, defs, gid):
    stops = []
    for gs in qa(gf, 'a:gsLst/a:gs'):
        c = parse_color(pkg, gs)
        stops.append((int(gs.get('pos')) / 100000.0, c))
    stops.sort(key=lambda s: s[0])
    lin = q(gf, 'a:lin')
    ang = int(lin.get('ang', '0')) / 60000.0 if lin is not None else 90.0
    path = q(gf, 'a:path')
    st = ''.join('<stop offset="%s" stop-color="%s"%s/>' % (
        fmt(p), c.css(1)[:7] if c.a >= .999 else '#%02x%02x%02x' % tuple(round(x * 255) for x in c.rgb),
        '' if c.a >= .999 else ' stop-opacity="%s"' % ('%.3f' % c.a)) for p, c in stops)
    if path is not None:
        ftr = q(path, 'a:fillToRect')
        l = int(ftr.get('l', '0')) / 1e5 if ftr is not None else .5
        t = int(ftr.get('t', '0')) / 1e5 if ftr is not None else .5
        cx, cy = w * l, h * t
        r = max(math.hypot(cx - x, cy - y) for x in (0, w) for y in (0, h))
        return '<radialGradient id="%s" gradientUnits="userSpaceOnUse" cx="%s" cy="%s" r="%s">%s</radialGradient>' % (
            gid, fmt(cx), fmt(cy), fmt(r), st)
    # DrawingML linear: angle measured clockwise, gradient line through centre,
    # length so that the corners are reached (scaled=0).
    t = math.radians(ang)
    dx, dy = math.cos(t), math.sin(t)
    half = (abs(w * dx) + abs(h * dy)) / 2.0
    cx, cy = w / 2.0, h / 2.0
    return '<linearGradient id="%s" gradientUnits="userSpaceOnUse" x1="%s" y1="%s" x2="%s" y2="%s">%s</linearGradient>' % (
        gid, fmt(cx - dx * half), fmt(cy - dy * half), fmt(cx + dx * half), fmt(cy + dy * half), st)


def grad_css(pkg, gf):
    stops = []
    for gs in qa(gf, 'a:gsLst/a:gs'):
        c = parse_color(pkg, gs)
        stops.append((int(gs.get('pos')) / 100000.0, c))
    stops.sort(key=lambda s: s[0])
    lin = q(gf, 'a:lin')
    ang = int(lin.get('ang', '0')) / 60000.0 if lin is not None else 90.0
    return 'linear-gradient(%sdeg,%s)' % (fmt(ang + 90), ','.join('%s %s%%' % (c.css(), fmt(p * 100)) for p, c in stops))


# --------------------------------------------------------------------------- geometry
def geom_path(prst, avs, w, h):
    """Return SVG path data for preset geometry in a w x h box."""
    if prst in ('rect', None):
        return 'M0 0H%sV%sH0Z' % (fmt(w), fmt(h))
    if prst == 'roundRect':
        adj = avs.get('adj', 16667) / 100000.0
        r = min(w, h) * adj
        return rrect(0, 0, w, h, r, r, r, r)
    if prst == 'round2SameRect':
        a1 = avs.get('adj1', 16667) / 100000.0
        a2 = avs.get('adj2', 0) / 100000.0
        r1, r2 = min(w, h) * a1, min(w, h) * a2
        return rrect(0, 0, w, h, r1, r1, r2, r2)
    if prst == 'ellipse':
        rx, ry = w / 2, h / 2
        return 'M0 %sA%s %s 0 1 0 %s %sA%s %s 0 1 0 0 %sZ' % (
            fmt(ry), fmt(rx), fmt(ry), fmt(w), fmt(ry), fmt(rx), fmt(ry), fmt(ry))
    if prst in ('line', 'straightConnector1'):
        return 'M0 0L%s %s' % (fmt(w), fmt(h))
    return 'M0 0H%sV%sH0Z' % (fmt(w), fmt(h))


def rrect(x, y, w, h, tl, tr, br, bl):
    f = fmt
    return ('M%s %sH%sA%s %s 0 0 1 %s %sV%sA%s %s 0 0 1 %s %sH%sA%s %s 0 0 1 %s %sV%sA%s %s 0 0 1 %s %sZ' % (
        f(x + tl), f(y), f(x + w - tr), f(tr), f(tr), f(x + w), f(y + tr), f(y + h - br), f(br), f(br),
        f(x + w - br), f(y + h), f(x + bl), f(bl), f(bl), f(x), f(y + h - bl), f(y + tl), f(tl), f(tl), f(x + tl), f(y)))


def cust_path(cg, w, h):
    out = []
    for path in qa(cg, 'a:pathLst/a:path'):
        pw = float(path.get('w', '0')) or None
        ph = float(path.get('h', '0')) or None
        sx = w / pw if pw else 1 / EMU_PX
        sy = h / ph if ph else 1 / EMU_PX
        d = []
        cur = (0, 0)
        start = (0, 0)
        for cmd in path:
            ln = etree.QName(cmd).localname
            pts = [(float(pt.get('x')) * sx, float(pt.get('y')) * sy) for pt in qa(cmd, 'a:pt')]
            if ln == 'moveTo':
                cur = start = pts[0]
                d.append('M%s %s' % (fmt(pts[0][0]), fmt(pts[0][1])))
            elif ln == 'lnTo':
                cur = pts[0]
                d.append('L%s %s' % (fmt(pts[0][0]), fmt(pts[0][1])))
            elif ln == 'cubicBezTo':
                d.append('C' + ' '.join('%s %s' % (fmt(x), fmt(y)) for x, y in pts))
                cur = pts[-1]
            elif ln == 'quadBezTo':
                d.append('Q' + ' '.join('%s %s' % (fmt(x), fmt(y)) for x, y in pts))
                cur = pts[-1]
            elif ln == 'arcTo':
                wr = float(cmd.get('wR')) * sx
                hr = float(cmd.get('hR')) * sy
                st = math.radians(int(cmd.get('stAng')) / 60000.0)
                sw = math.radians(int(cmd.get('swAng')) / 60000.0)
                cx = cur[0] - wr * math.cos(st)
                cy = cur[1] - hr * math.sin(st)
                en = st + sw
                ex, ey = cx + wr * math.cos(en), cy + hr * math.sin(en)
                large = 1 if abs(sw) > math.pi else 0
                sweep = 1 if sw > 0 else 0
                d.append('A%s %s 0 %d %d %s %s' % (fmt(wr), fmt(hr), large, sweep, fmt(ex), fmt(ey)))
                cur = (ex, ey)
            elif ln == 'close':
                d.append('Z')
                cur = start
        out.append((' '.join(d), path.get('fill') != 'none', path.get('stroke') != 'false'))
    return out


# --------------------------------------------------------------------------- converter
class Conv:
    def __init__(self, pkg, outdir, deck):
        self.pkg, self.outdir, self.deck = pkg, outdir, deck
        self.media = {}            # src path -> out rel path
        self.defs = Defs()
        os.makedirs(os.path.join(outdir, 'media'), exist_ok=True)

    # ---- media
    def media_url(self, part, rid):
        src = part.rel(rid)
        if not src:
            return None
        if src in self.media:
            return self.media[src]
        ext = os.path.splitext(src)[1].lower()
        name = os.path.basename(src)
        if ext == '.svg':
            # keep the svg as-is
            pass
        dst = 'media/' + name
        shutil.copy(os.path.join(self.pkg.root, src), os.path.join(self.outdir, dst))
        self.media[src] = dst
        return dst

    # ---- text style resolution
    def lvl_props(self, lst, lvl):
        if lst is None:
            return None
        return q(lst, 'a:lvl%dpPr' % (lvl + 1))

    def text_chain(self, ph_type, inherited_lsts, own_lst, lvl):
        """Return list of lvlNpPr elements from most generic to most specific."""
        chain = []
        dts = q(self.pkg.pres.xml, 'p:defaultTextStyle')
        chain.append(self.lvl_props(dts, lvl))
        txs = q(self.pkg.master.xml, 'p:txStyles')
        if ph_type in ('title', 'ctrTitle'):
            chain.append(self.lvl_props(q(txs, 'p:titleStyle'), lvl))
        elif ph_type in ('body', 'subTitle', 'obj', None) and ph_type is not None:
            chain.append(self.lvl_props(q(txs, 'p:bodyStyle'), lvl))
        for l in inherited_lsts:
            chain.append(self.lvl_props(l, lvl))
        chain.append(self.lvl_props(own_lst, lvl))
        return [c for c in chain if c is not None]

    def font_css(self, face):
        if face is None:
            return None
        if face.startswith('+mj'):
            face = self.pkg.major
        elif face.startswith('+mn'):
            face = self.pkg.minor
        f = face.lower()
        if f.startswith('archivo'):
            if 'semiexpand' in f:
                return "'Archivo'", 'font-stretch:112.5%;'
            if 'expanded' in f:
                return "'Archivo'", 'font-stretch:125%;'
            return "'Archivo'", ''
        if 'plex mono' in f:
            return "'IBM Plex Mono'", ''
        if 'funnel' in f:
            return "'Funnel Sans'", ''
        if 'barlow' in f:
            return "'Barlow'", ''
        return "'%s'" % face, ''

    def run_style(self, rprs, phclr=None, scale=1.0):
        """rprs: list of rPr/defRPr elements generic->specific. returns css string."""
        st = {}
        for r in rprs:
            if r is None:
                continue
            for k in ('sz', 'b', 'i', 'cap', 'spc', 'baseline', 'u'):
                if r.get(k) is not None:
                    st[k] = r.get(k)
            fl = q(r, 'a:solidFill')
            if fl is not None:
                st['color'] = parse_color(self.pkg, fl)
            if q(r, 'a:noFill') is not None:
                st['color'] = Color((0, 0, 0), 0)
            gf = q(r, 'a:gradFill')
            if gf is not None:
                st['grad'] = gf
            lat = q(r, 'a:latin')
            if lat is not None and lat.get('typeface'):
                st['font'] = lat.get('typeface')
        css = []
        size = int(st.get('sz', '1800')) / 100.0 * PT_PX * scale
        css.append('font-size:%spx' % fmt(size))
        fam = self.font_css(st.get('font', '+mn-lt'))
        if fam:
            css.append('font-family:%s' % fam[0])
            if fam[1]:
                css.append(fam[1].rstrip(';'))
        css.append('font-weight:%s' % ('700' if st.get('b') == '1' else '400'))
        if st.get('i') == '1':
            css.append('font-style:italic')
        if st.get('cap') == 'all':
            css.append('text-transform:uppercase')
        elif st.get('cap') == 'small':
            css.append('font-variant:small-caps')
        if st.get('spc') and st.get('spc') != '0':
            css.append('letter-spacing:%spx' % fmt(int(st['spc']) / 100.0 * PT_PX * scale))
        if st.get('u') and st.get('u') != 'none':
            css.append('text-decoration:underline')
        if st.get('baseline') and st.get('baseline') != '0':
            b = int(st['baseline']) / 1000.0
            css.append('vertical-align:%s%%' % fmt(b))
            css.append('font-size:%spx' % fmt(size * .66))
        if 'grad' in st:
            css.append('background:%s;-webkit-background-clip:text;background-clip:text;color:transparent' % grad_css(self.pkg, st['grad']))
        else:
            c = st.get('color') or phclr
            if c is not None:
                css.append('color:%s' % c.css())
        return ';'.join(css), size

    def text_html(self, txb, w, h, ph_type, inherited, phclr=None, inherited_body=None):
        body = q(txb, 'a:bodyPr')
        bodies = [b for b in (inherited_body or []) if b is not None] + ([body] if body is not None else [])
        bp = {}
        for b in bodies:
            bp.update(b.attrib)
        l = px(bp.get('lIns', 91440)); r_ = px(bp.get('rIns', 91440))
        t = px(bp.get('tIns', 45720)); b_ = px(bp.get('bIns', 45720))
        anchor = bp.get('anchor', 't')
        wrap = bp.get('wrap', 'square')
        scale, lnred = 1.0, 0.0
        for b in bodies:
            na = q(b, 'a:normAutofit')
            if na is not None:
                scale = int(na.get('fontScale', '100000')) / 100000.0
                lnred = int(na.get('lnSpcReduction', '0')) / 100000.0
        own_lst = q(txb, 'a:lstStyle')
        paras = qa(txb, 'a:p')
        # empty?
        if not any((r.text or '').strip() for p in paras for r in qa(p, './/a:t')):
            return ''
        parts = []
        for p in paras:
            ppr = q(p, 'a:pPr')
            lvl = int(ppr.get('lvl', '0')) if ppr is not None else 0
            chain = self.text_chain(ph_type, inherited, own_lst, lvl) + ([ppr] if ppr is not None else [])
            pp = {}
            lnspc = None; spcb = 0; spca = 0
            bullet = None
            for c in chain:
                pp.update({k: v for k, v in c.attrib.items()})
                ls = q(c, 'a:lnSpc/a:spcPct')
                if ls is not None:
                    lnspc = ('pct', int(ls.get('val')) / 100000.0)
                ls = q(c, 'a:lnSpc/a:spcPts')
                if ls is not None:
                    lnspc = ('pts', int(ls.get('val')) / 100.0)
                sb = q(c, 'a:spcBef/a:spcPts')
                if sb is not None:
                    spcb = int(sb.get('val')) / 100.0 * PT_PX
                sa = q(c, 'a:spcAft/a:spcPts')
                if sa is not None:
                    spca = int(sa.get('val')) / 100.0 * PT_PX
                if q(c, 'a:buNone') is not None:
                    bullet = None
                bc = q(c, 'a:buChar')
                if bc is not None:
                    bullet = bc.get('char')
            defr = [q(c, 'a:defRPr') for c in chain]
            runs = []
            maxsize = 0
            for r in p:
                ln = etree.QName(r).localname
                if ln in ('r', 'fld'):
                    rpr = q(r, 'a:rPr')
                    css, size = self.run_style(defr + [rpr], phclr, scale)
                    maxsize = max(maxsize, size)
                    txt = q(r, 'a:t')
                    txt = txt.text if txt is not None and txt.text else ''
                    runs.append('<span style="%s">%s</span>' % (css, esc(txt)))
                elif ln == 'br':
                    rpr = q(r, 'a:rPr')
                    css, size = self.run_style(defr + [rpr], phclr, scale)
                    runs.append('<br>')
            if not runs:
                epr = q(p, 'a:endParaRPr')
                css, size = self.run_style(defr + [epr], phclr, scale)
                maxsize = size
                runs.append('<span style="%s">&#8203;</span>' % css)
            algn = {'l': 'left', 'ctr': 'center', 'r': 'right', 'just': 'justify', 'dist': 'justify'}.get(pp.get('algn', 'l'), 'left')
            pcss = ['text-align:%s' % algn]
            if lnspc and lnspc[0] == 'pct':
                pcss.append('line-height:%s' % fmt(max(.6, (lnspc[1] - lnred)) * 1.2 * 100 / 100) )
            elif lnspc:
                pcss.append('line-height:%spx' % fmt(lnspc[1] * PT_PX))
            else:
                pcss.append('line-height:%s' % fmt((1 - lnred) * 1.2))
            if spcb:
                pcss.append('margin-top:%spx' % fmt(spcb * scale))
            if spca:
                pcss.append('margin-bottom:%spx' % fmt(spca * scale))
            marL = px(pp.get('marL', 0)); ind = px(pp.get('indent', 0))
            if marL:
                pcss.append('padding-left:%spx' % fmt(marL))
            if ind and bullet:
                pcss.append('text-indent:%spx' % fmt(ind))
            pre = ''
            if bullet:
                pre = '<span class="bu">%s</span>' % esc(bullet)
            parts.append('<p style="%s">%s%s</p>' % (';'.join(pcss), pre, ''.join(runs)))
        jc = {'t': 'flex-start', 'ctr': 'center', 'b': 'flex-end'}.get(anchor, 'flex-start')
        tcss = 'padding:%spx %spx %spx %spx;justify-content:%s' % (fmt(t), fmt(r_), fmt(b_), fmt(l), jc)
        if wrap == 'none':
            tcss += ';white-space:nowrap'
            if bp.get('anchor') == 'ctr' or True:
                pass
        return '<div class="tx" style="%s">%s</div>' % (tcss, ''.join(parts))

    # ---- fills & lines
    def fill_of(self, sppr, part, style=None):
        """returns ('none'|'solid'|'grad'|'blip', payload)"""
        if sppr is None:
            sppr = etree.Element('x')
        for ch in sppr:
            ln = etree.QName(ch).localname
            if ln == 'noFill':
                return ('none', None)
            if ln == 'solidFill':
                return ('solid', parse_color(self.pkg, ch))
            if ln == 'gradFill':
                return ('grad', ch)
            if ln == 'blipFill':
                return ('blip', ch)
        if style is not None:
            fr = q(style, 'a:fillRef')
            if fr is not None and fr.get('idx') not in ('0', None):
                return ('solid', parse_color(self.pkg, fr))
        return ('none', None)

    def line_of(self, sppr, style=None):
        ln = q(sppr, 'a:ln')
        color = None; w = None; dash = None; head = tail = None
        if style is not None:
            lr = q(style, 'a:lnRef')
            if lr is not None and lr.get('idx') not in ('0', None):
                color = parse_color(self.pkg, lr)
                w = 1.0
        if ln is not None:
            if ln.get('w'):
                w = px(ln.get('w'))
            if q(ln, 'a:noFill') is not None:
                return None
            sf = q(ln, 'a:solidFill')
            if sf is not None:
                color = parse_color(self.pkg, sf)
                if w is None:
                    w = 1.0
            gf = q(ln, 'a:gradFill')
            if gf is not None:
                color = ('grad', gf)
                if w is None:
                    w = 1.0
            pd = q(ln, 'a:prstDash')
            if pd is not None and pd.get('val') != 'solid':
                dash = pd.get('val')
            he = q(ln, 'a:headEnd'); te = q(ln, 'a:tailEnd')
            head = he.get('type') if he is not None and he.get('type') not in (None, 'none') else None
            tail = te.get('type') if te is not None and te.get('type') not in (None, 'none') else None
        if color is None:
            return None
        return dict(color=color, w=max(w or 1.0, .5), dash=dash, head=head, tail=tail)

    # ---- elements
    def xfrm(self, el):
        x = q(el, 'a:xfrm') if el is not None else None
        if x is None:
            x = q(el, 'p:xfrm')
        if x is None:
            return None
        off = q(x, 'a:off'); ext = q(x, 'a:ext')
        if off is None or ext is None:
            return None
        d = dict(x=px(off.get('x')), y=px(off.get('y')), w=px(ext.get('cx')), h=px(ext.get('cy')),
                 rot=int(x.get('rot', '0')) / 60000.0, fh=x.get('flipH') == '1', fv=x.get('flipV') == '1')
        cho = q(x, 'a:chOff'); che = q(x, 'a:chExt')
        if cho is not None:
            d.update(cx=px(cho.get('x')), cy=px(cho.get('y')), cw=px(che.get('cx')), ch=px(che.get('cy')))
        return d

    def box_css(self, b):
        css = 'left:%spx;top:%spx;width:%spx;height:%spx' % (fmt(b['x']), fmt(b['y']), fmt(b['w']), fmt(b['h']))
        tr = []
        if b.get('rot'):
            tr.append('rotate(%sdeg)' % fmt(b['rot']))
        if b.get('fh'):
            tr.append('scaleX(-1)')
        if b.get('fv'):
            tr.append('scaleY(-1)')
        if tr:
            css += ';transform:' + ' '.join(tr)
        return css

    def placeholder_info(self, sp, part):
        ph = q(sp, './/p:nvPr/p:ph')
        if ph is None:
            return None
        return ph.get('type', 'body'), ph.get('idx')

    def find_ph(self, part, ptype, idx):
        """find matching placeholder sp in layout/master."""
        for sp in part.xml.iter(P + 'sp'):
            ph = q(sp, './/p:nvPr/p:ph')
            if ph is None:
                continue
            t = ph.get('type', 'body')
            if idx is not None and ph.get('idx') == idx:
                return sp
            if idx is None and t == ptype:
                return sp
        for sp in part.xml.iter(P + 'sp'):
            ph = q(sp, './/p:nvPr/p:ph')
            if ph is not None and ph.get('type', 'body') == ptype:
                return sp
        return None

    def shape(self, sp, part, ctx, box):
        """Render p:sp. box = absolute box in px (already transformed)."""
        sppr = q(sp, 'p:spPr')
        style = q(sp, 'p:style')
        phinfo = self.placeholder_info(sp, part)
        inherited = []
        inherited_body = []
        if phinfo:
            for lp in ctx.get('ph_parts', []):
                psp = self.find_ph(lp, phinfo[0], phinfo[1])
                if psp is not None:
                    inherited.insert(0, q(psp, 'p:txBody/a:lstStyle'))
                    inherited_body.insert(0, q(psp, 'p:txBody/a:bodyPr'))
        w, h = box['w'], box['h']
        out = []
        # geometry
        pg = q(sppr, 'a:prstGeom'); cg = q(sppr, 'a:custGeom')
        prst = pg.get('prst') if pg is not None else None
        avs = {}
        if pg is not None:
            for gd in qa(pg, 'a:avLst/a:gd'):
                m = re.match(r'val (-?\d+)', gd.get('fmla', ''))
                if m:
                    avs[gd.get('name')] = int(m.group(1))
        ftype, fpay = self.fill_of(sppr, part, style)
        line = self.line_of(sppr, style)
        svg = ''
        if ftype != 'none' or line:
            svg = self.shape_svg(prst, avs, cg, w, h, ftype, fpay, line, part)
        txb = q(sp, 'p:txBody')
        phclr = None
        if style is not None:
            fr = q(style, 'a:fontRef')
            if fr is not None:
                phclr = parse_color(self.pkg, fr)
        txt = self.text_html(txb, w, h, phinfo[0] if phinfo else None, inherited, phclr, inherited_body) if txb is not None else ''
        if not svg and not txt:
            return ''
        return '<div class="s" style="%s">%s%s</div>' % (self.box_css(box), svg, txt)

    def shape_svg(self, prst, avs, cg, w, h, ftype, fpay, line, part):
        defs = []
        lw = line['w'] if line else 0
        pad = lw + (6 * lw if line and (line['head'] or line['tail']) else 0) + 1
        if cg is not None:
            paths = cust_path(cg, w, h)
        else:
            paths = [(geom_path(prst, avs, w, h), prst not in ('line', 'straightConnector1'), True)]
        fill = 'none'
        if ftype == 'solid' and fpay is not None:
            fill = fpay.css()
        elif ftype == 'grad':
            gid = self.defs.id(self.deck + 'g')
            defs.append(grad_svg(self.pkg, fpay, w, h, None, gid))
            fill = 'url(#%s)' % gid
        elif ftype == 'blip':
            blip = q(fpay, 'a:blip')
            url = self.media_url(part, blip.get(R + 'embed')) if blip is not None else None
            if url:
                pid = self.defs.id(self.deck + 'p')
                defs.append('<pattern id="%s" patternUnits="userSpaceOnUse" width="%s" height="%s"><image href="%s" width="%s" height="%s" preserveAspectRatio="none"/></pattern>' % (pid, fmt(w), fmt(h), url, fmt(w), fmt(h)))
                fill = 'url(#%s)' % pid
        stroke = ''
        if line:
            c = line['color']
            if isinstance(c, tuple):
                gid = self.defs.id(self.deck + 'g')
                defs.append(grad_svg(self.pkg, c[1], w, h, None, gid))
                sc = 'url(#%s)' % gid
            else:
                sc = c.css()
            stroke = ' stroke="%s" stroke-width="%s"' % (sc, fmt(lw))
            if line['dash']:
                d = {'dash': (4, 3), 'sysDash': (3, 1), 'sysDot': (1, 1), 'dot': (1, 2), 'lgDash': (8, 3)}.get(line['dash'], (4, 3))
                stroke += ' stroke-dasharray="%s"' % ' '.join(fmt(x * lw) for x in d)
            for end, key in (('head', 'marker-start'), ('tail', 'marker-end')):
                if line[end]:
                    mid = self.defs.id(self.deck + 'm')
                    col = sc if not sc.startswith('url') else '#fff'
                    if end == 'tail':
                        defs.append('<marker id="%s" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4" markerHeight="4" orient="auto"><path d="M0 0L10 5L0 10Z" fill="%s"/></marker>' % (mid, col))
                    else:
                        defs.append('<marker id="%s" viewBox="0 0 10 10" refX="2" refY="5" markerWidth="4" markerHeight="4" orient="auto"><path d="M10 0L0 5L10 10Z" fill="%s"/></marker>' % (mid, col))
                    stroke += ' %s="url(#%s)"' % (key, mid)
        body = ''
        for d, dofill, dostroke in paths:
            body += '<path d="%s" fill="%s"%s/>' % (d, fill if dofill else 'none', stroke if dostroke else '')
        return '<svg class="g" viewBox="%s %s %s %s" style="left:%spx;top:%spx;width:%spx;height:%spx" overflow="visible">%s%s</svg>' % (
            fmt(-pad), fmt(-pad), fmt(w + 2 * pad), fmt(h + 2 * pad), fmt(-pad), fmt(-pad), fmt(w + 2 * pad), fmt(h + 2 * pad),
            ('<defs>%s</defs>' % ''.join(defs)) if defs else '', body)

    def picture(self, pic, part, box):
        bf = q(pic, 'p:blipFill')
        blip = q(bf, 'a:blip')
        if blip is None:
            return ''
        svgb = q(blip, './/asvg:svgBlip')
        rid = svgb.get(R + 'embed') if svgb is not None else blip.get(R + 'embed')
        url = self.media_url(part, rid)
        if not url:
            return ''
        css = []
        am = q(blip, 'a:alphaModFix')
        op = int(am.get('amt', '100000')) / 100000.0 if am is not None else 1.0
        filt = []
        for eff in qa(blip, './/a14:imgEffect'):
            s = q(eff, 'a14:saturation')
            if s is not None:
                filt.append('saturate(%s)' % fmt(int(s.get('sat')) / 100000.0))
            ct = q(eff, 'a14:colorTemperature')
            if ct is not None:
                k = int(ct.get('colorTemp'))
                # small warm/cool shift around 6500K neutral
                if k < 6500:
                    filt.append('sepia(%s)' % fmt(min(.25, (6500 - k) / 6000.0)))
            bc = q(eff, 'a14:brightnessContrast')
            if bc is not None:
                filt.append('brightness(%s)' % fmt(1 + int(bc.get('bright', '0')) / 100000.0))
                filt.append('contrast(%s)' % fmt(1 + int(bc.get('contrast', '0')) / 100000.0))
        if q(blip, 'a:grayscl') is not None:
            filt.append('grayscale(1)')
        sr = q(bf, 'a:srcRect')
        l = t = r = b = 0.0
        if sr is not None:
            l, t, r, b = (int(sr.get(k, '0')) / 100000.0 for k in ('l', 't', 'r', 'b'))
        sppr = q(pic, 'p:spPr')
        pg = q(sppr, 'a:prstGeom')
        radius = ''
        if pg is not None and pg.get('prst') == 'roundRect':
            adj = 16667
            gd = q(pg, 'a:avLst/a:gd')
            if gd is not None:
                adj = int(re.search(r'-?\d+', gd.get('fmla')).group(0))
            radius = 'border-radius:%spx;' % fmt(min(box['w'], box['h']) * adj / 100000.0)
        elif pg is not None and pg.get('prst') == 'ellipse':
            radius = 'border-radius:50%;'
        elif pg is not None and pg.get('prst') == 'round2SameRect':
            gd = {g.get('name'): int(re.search(r'-?\d+', g.get('fmla')).group(0)) for g in qa(pg, 'a:avLst/a:gd')}
            r1 = min(box['w'], box['h']) * gd.get('adj1', 16667) / 100000.0
            radius = 'border-radius:%spx %spx 0 0;' % (fmt(r1), fmt(r1))
        iw = 1.0 / max(.0001, 1 - l - r); ih = 1.0 / max(.0001, 1 - t - b)
        style = 'left:%s%%;top:%s%%;width:%s%%;height:%s%%' % (fmt(-l * iw * 100), fmt(-t * ih * 100), fmt(iw * 100), fmt(ih * 100))
        if filt:
            style += ';filter:' + ' '.join(filt)
        cls = 'pic'
        big = box['w'] * box['h'] > 1920 * 1080 * .45
        if big and not url.endswith('.svg'):
            cls += ' kb'
        line = self.line_of(sppr)
        border = ''
        if line and not isinstance(line['color'], tuple):
            border = 'box-shadow:inset 0 0 0 %spx %s;' % (fmt(line['w']), line['color'].css())
        alt = q(pic, 'p:nvPicPr/p:cNvPr').get('descr') or ''
        ov = '<i class="bd" style="%s%s"></i>' % (radius, border) if border else ''
        return '<div class="%s" style="%s;%s%s"><img src="%s" alt="%s" style="%s" draggable="false">%s</div>' % (
            cls, self.box_css(box), radius, ('opacity:%s;' % fmt(op)) if op < 1 else '', url, esc(alt), style, ov)

    def connector(self, cx, part, box):
        sppr = q(cx, 'p:spPr')
        style = q(cx, 'p:style')
        line = self.line_of(sppr, style)
        if not line:
            return ''
        pg = q(sppr, 'a:prstGeom')
        prst = pg.get('prst') if pg is not None else 'line'
        if prst not in ('line', 'straightConnector1'):
            # bent connectors etc: draw as straight line
            prst = 'line'
        svg = self.shape_svg(prst, {}, None, box['w'], box['h'], 'none', None, line, part)
        return '<div class="s" style="%s">%s</div>' % (self.box_css(box), svg)

    def walk(self, tree, part, ctx, transform=None):
        """yield (name, html) for each child of an spTree / grpSp."""
        items = []
        for el in tree:
            ln = etree.QName(el).localname
            if ln == 'AlternateContent':
                ch = q(el, 'mc:Choice')
                if ch is not None:
                    items += self.walk(ch, part, ctx, transform)
                continue
            if ln not in ('sp', 'pic', 'grpSp', 'cxnSp', 'graphicFrame'):
                continue
            nv = el.find('.//' + P + 'cNvPr')
            name = nv.get('name', '') if nv is not None else ''
            if nv is not None and nv.get('hidden') == '1':
                continue
            sppr = q(el, 'p:spPr') if ln != 'grpSp' else q(el, 'p:grpSpPr')
            b = self.xfrm(sppr)
            if ln == 'sp' and b is None:
                ph = self.placeholder_info(el, part)
                if ph:
                    for lp in ctx.get('ph_parts', []):
                        psp = self.find_ph(lp, ph[0], ph[1])
                        if psp is not None:
                            b = self.xfrm(q(psp, 'p:spPr'))
                            if b:
                                break
            if b is None:
                continue
            if transform:
                b = transform(b)
            if ln == 'grpSp':
                g = b
                sx = g['w'] / g['cw'] if g.get('cw') else 1
                sy = g['h'] / g['ch'] if g.get('ch') else 1

                def tf(cb, g=g, sx=sx, sy=sy):
                    nb = dict(cb)
                    nb['x'] = g['x'] + (cb['x'] - g['cx']) * sx
                    nb['y'] = g['y'] + (cb['y'] - g['cy']) * sy
                    nb['w'] = cb['w'] * sx
                    nb['h'] = cb['h'] * sy
                    if 'cx' in cb:
                        pass
                    return nb
                # group rotation/flip applied on the wrapper
                inner = self.walk(el, part, ctx, tf)
                gcss = ''
                tr = []
                if g.get('rot'):
                    tr.append('rotate(%sdeg)' % fmt(g['rot']))
                if g.get('fh'):
                    tr.append('scaleX(-1)')
                if g.get('fv'):
                    tr.append('scaleY(-1)')
                if tr:
                    gcss = ' style="transform-origin:%spx %spx;transform:%s"' % (
                        fmt(g['x'] + g['w'] / 2), fmt(g['y'] + g['h'] / 2), ' '.join(tr))
                items.append((name, '<div class="grp"%s>%s</div>' % (gcss, ''.join(h for _, h, _ in inner)), b))
                continue
            if ln == 'sp':
                h = self.shape(el, part, ctx, b)
            elif ln == 'pic':
                h = self.picture(el, part, b)
            elif ln == 'cxnSp':
                h = self.connector(el, part, b)
            else:
                h = ''
            if h:
                items.append((name, h, b))
        return items

    def bg(self, part):
        bg = q(part.xml, 'p:cSld/p:bg')
        if bg is None:
            return None
        bp = q(bg, 'p:bgPr')
        if bp is not None:
            t, pay = self.fill_of(bp, part)
            if t == 'solid':
                return 'background:%s' % pay.css()
            if t == 'grad':
                return 'background:%s' % grad_css(self.pkg, pay)
            if t == 'blip':
                url = self.media_url(part, q(pay, 'a:blip').get(R + 'embed'))
                return "background:url('%s') center/cover no-repeat" % url
        br = q(bg, 'p:bgRef')
        if br is not None:
            c = parse_color(self.pkg, br)
            if c:
                return 'background:%s' % c.css()
        return None

    def slide(self, path, n):
        sl = Part(self.pkg, path)
        lay = Part(self.pkg, sl.rel_of_type('slideLayout'))
        mas = self.pkg.master
        ctx = {'ph_parts': [lay, mas]}
        bgcss = self.bg(sl) or self.bg(lay) or self.bg(mas) or 'background:#000'
        layers = []
        show_master = sl.xml.get('showMasterSp') != '0'
        if show_master and lay.xml.get('showMasterSp') != '0':
            for name, h, b in self.walk_noph(q(mas.xml, 'p:cSld/p:spTree'), mas):
                layers.append(('m', name, h, b))
        if show_master:
            for name, h, b in self.walk_noph(q(lay.xml, 'p:cSld/p:spTree'), lay):
                layers.append(('l', name, h, b))
        for name, h, b in self.walk(q(sl.xml, 'p:cSld/p:spTree'), sl, ctx):
            layers.append(('s', name, h, b))
        tr = q(sl.xml, 'p:transition')
        if tr is None:
            ac = sl.xml.find('mc:AlternateContent/mc:Choice/p:transition', NS)
            tr = ac
        adv = None
        if tr is not None and tr.get('advTm'):
            adv = int(tr.get('advTm'))
        return bgcss, layers, adv

    def _is_ph_sp(self, h):
        return False

    def walk_noph(self, tree, part):
        # layout shapes that are not placeholders
        filtered = etree.Element('x')
        for el in tree:
            ln = etree.QName(el).localname
            if ln == 'sp' and q(el, './/p:nvPr/p:ph') is not None:
                continue
            filtered.append(el.__copy__() if False else el)
        res = self.walk(filtered, part, {'ph_parts': []})
        return res


DECOR = re.compile(r'(bloom|scrim|striation|decor|background|bg\b|overlay|texture|gradient|vignette)', re.I)


def classify(kind, name, box):
    """'bg' elements fade with the slide; others get the staggered entrance."""
    if kind in ('m', 'l'):
        return 'bg'
    if DECOR.search(name or ''):
        return 'bg'
    if box['w'] >= 1900 * .9 and box['h'] >= 1080 * .9:
        return 'bg'
    return 'fg'


def main():
    src, out, deck, title = sys.argv[1:5]
    pkg = Pkg(src)
    os.makedirs(out, exist_ok=True)
    conv = Conv(pkg, out, deck)
    slides = []
    for i, sp in enumerate(pkg.slides):
        bgcss, layers, adv = conv.slide(sp, i + 1)
        # order foreground elements top-to-bottom, left-to-right for the stagger
        fg = [l for l in layers if classify(l[0], l[1], l[3]) == 'fg']
        rank = {id(l): k for k, l in enumerate(sorted(fg, key=lambda l: (round(l[3]['y'] / 40), l[3]['x'])))}
        hs = []
        for l in layers:
            kind = classify(l[0], l[1], l[3])
            if kind == 'bg':
                hs.append('<div class="L bg">%s</div>' % l[2])
            else:
                k = rank[id(l)]
                hs.append('<div class="L fg" style="--i:%d">%s</div>' % (k, l[2]))
        slides.append(dict(bg=bgcss, html=''.join(hs), adv=adv or 7000))
    json.dump(dict(deck=deck, title=title, slides=slides, media=sorted(set(conv.media.values()))),
              open(os.path.join(out, 'slides.build.json'), 'w'))
    print(deck, len(slides), 'slides,', len(conv.media), 'media')


if __name__ == '__main__':
    main()
