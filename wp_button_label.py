import re
from PIL import Image, ImageDraw, ImageFont

# Draws a label centered on a button image (or a plain tile when there's no image).
# Shared by the Stream Deck keys and the on-screen favorites tiles so they look and fit text the same way.
def renderButtonLabel(size, label, image=None, fontSizes=[14, 12, 10], bgColor=(50, 70, 50),
                      fontPath='assets/PublicSans-Medium.ttf', padding=4, gap=4):
    if image is None:
        img = Image.new('RGB', size, bgColor)
        draw = ImageDraw.Draw(img)
    else:
        img = image.resize(size)
        draw = ImageDraw.Draw(img)

    w, h = size
    maxWidth = w - 2 * padding

    # try progressively smaller fonts before splitting/truncating
    font = None
    for fontSize in fontSizes:
        try:
            f = ImageFont.truetype(fontPath, fontSize)
        except:
            f = ImageFont.load_default()
        font = f
        bbox = draw.textbbox((0, 0), label, font=font)
        if bbox[2] - bbox[0] <= maxWidth:
            break  # fits at this size

    # try to fit on one line first
    bbox = draw.textbbox((0, 0), label, font=font)
    if bbox[2] - bbox[0] > maxWidth:
        # try balanced two-line split
        words = re.split(r'\s+|(?<=\-)', label)
        bestSplit = None
        bestDiff = float('inf')

        for i in range(1, len(words)):
            line1 = ' '.join(words[:i])
            line2 = ' '.join(words[i:])
            w1 = draw.textbbox((0, 0), line1, font=font)[2]
            w2 = draw.textbbox((0, 0), line2, font=font)[2]
            if w1 > maxWidth or w2 > maxWidth:
                continue
            diff = abs(w1 - w2)
            if diff < bestDiff:
                bestDiff = diff
                bestSplit = i

        if bestSplit:
            lines = [' '.join(words[:bestSplit]), ' '.join(words[bestSplit:])]
        else:
            # truncate single line
            text = label
            while text and draw.textbbox((0, 0), text + '...', font=font)[2] > maxWidth:
                text = text[:-1]
            lines = [text + '...']
    else:
        lines = [label]

    # measure and draw centered
    lineHeight = draw.textbbox((0, 0), 'Ag', font=font)[3]
    totalH = len(lines) * lineHeight + (len(lines) - 1) * gap
    startY = (h - totalH) // 2

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (w - (bbox[2] - bbox[0])) // 2
        y = startY + i * (lineHeight + gap) - bbox[1]
        draw.text((x + 1, y + 1), line, font=font, fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=(255, 255, 255))

    return img
