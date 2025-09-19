import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from PIL.ExifTags import TAGS


def get_exif_datetime(img_path):
    """
    从图片中读取EXIF中的拍摄时间信息
    返回年月日格式字符串，例如 "2023-05-19"
    """
    try:
        image = Image.open(img_path)
        exif_data = image._getexif()  # 获取exif原始数据
        if not exif_data:
            return None

        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, tag_id)
            if tag == "DateTimeOriginal":
                # 一般格式为 "2023:05:19 12:34:56"
                date_part = value.split(" ")[0]  # 只取日期部分
                date_part = date_part.replace(":", "-")  # 替换为常见日期格式
                return date_part
    except Exception as e:
        print(f"读取EXIF失败: {e}")
        return None
    return None


def add_watermark(img_path, text, font_size, color, position):
    """
    给图片添加水印并保存到新目录
    """
    image = Image.open(img_path)
    draw = ImageDraw.Draw(image)

    # 尝试加载系统字体，如果失败则用PIL默认字体
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except:
        font = ImageFont.load_default()

    # 获取文字尺寸（兼容旧版和新版Pillow）
    try:
        # 新版 Pillow 推荐 textbbox
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        # 老版本 Pillow 还支持 textsize
        text_width, text_height = draw.textsize(text, font=font)

    img_width, img_height = image.size

    # 根据位置计算坐标
    if position == "left_top":
        x, y = 10, 10
    elif position == "right_top":
        x, y = img_width - text_width - 10, 10
    elif position == "left_bottom":
        x, y = 10, img_height - text_height - 10
    elif position == "right_bottom":
        x, y = img_width - text_width - 10, img_height - text_height - 10
    elif position == "center":
        x, y = (img_width - text_width) // 2, (img_height - text_height) // 2
    else:
        x, y = 10, 10  # 默认左上角

    # 绘制文字
    draw.text((x, y), text, fill=color, font=font)

    # 构造输出路径
    img_path = Path(img_path)
    output_dir = img_path.parent / f"{img_path.parent.name}_watermark"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / img_path.name

    # 保存图片
    image.save(output_path)
    print(f"已保存水印图片: {output_path}")


def main():
    # 输入图片路径
    img_path = input("请输入图片文件路径: ").strip()
    if not os.path.isfile(img_path):
        print("路径无效，请检查文件路径。")
        return

    # 获取拍摄日期
    date_text = get_exif_datetime(img_path)
    if not date_text:
        print("未能读取到EXIF拍摄时间，将使用默认文本。")
        date_text = "NoDate"

    # 设置参数
    font_size = int(input("请输入字体大小（如30）: ").strip() or 30)
    color = input("请输入字体颜色（如 red 或 #FF0000）: ").strip() or "red"
    print("请选择位置: left_top / right_top / left_bottom / right_bottom / center")
    position = input("请输入水印位置: ").strip() or "right_bottom"

    # 添加水印
    add_watermark(img_path, date_text, font_size, color, position)


if __name__ == "__main__":
    main()
