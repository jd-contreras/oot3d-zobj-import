"""Bake previews of tunic-tinted (ZZENV) materials in each tunic colour."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

# OoT3D-style saturated tunic colours (N64 values were Kokiri 30,105,27 / Goron 100,20,0 / Zora 0,60,100)
TUNICS = {
    'kokiri': (0x1A, 0xB3, 0x1A),
    'goron': (0xC3, 0x08, 0x19),
    'zora': (0x11, 0x44, 0xBB),
}

if __name__ == '__main__':
    from PIL import Image
    import zobj, cmbskel, pose, render
    zpath, cmbpath, out = sys.argv[1:4]
    m = zobj.read(zpath)
    bones, world = cmbskel.read_skeleton(open(cmbpath, 'rb').read())
    lw, _, _ = pose.fit(m, bones, world)
    placed = pose.place(m, lw)
    ims = [render.render(placed, m, None, size=500, tunic=c) for c in TUNICS.values()]
    sheet = Image.new('RGB', (ims[0].width, sum(i.height for i in ims)))
    y = 0
    for im in ims:
        sheet.paste(im, (0, y))
        y += im.height
    sheet.save(out)
