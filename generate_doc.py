#!/usr/bin/env python3
"""
Script tạo tài liệu hướng dẫn AI Đánh Giá Thử Việc
theo đúng mẫu DAIT - thay nội dung và ảnh thực tế
"""

import os
import copy
import shutil
from docx import Document
from docx.shared import Inches, Pt, RGBColor, Cm, Emu
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn, nsmap
from docx.oxml import OxmlElement
import lxml.etree as etree

# Paths
TEMPLATE_PATH = '/Users/_qh.fol_/frappe-bench/apps/ai_ats/DAIT-Tài liệu mô tả AI Agent-Đánh Giá Thử Việc-2026.docx'
OUTPUT_PATH = '/Users/_qh.fol_/frappe-bench/apps/ai_ats/DAIT-Tài-liệu-hướng-dẫn-AI-Đánh-Giá-Thử-Việc-2026.docx'
IMAGES_DIR = '/Users/_qh.fol_/frappe-bench/apps/ai_ats/docx_images'

# Image mapping: image files from docx
IMG_LOGO    = os.path.join(IMAGES_DIR, 'image1.png')   # CT Group logo
IMG_SCREEN1 = os.path.join(IMAGES_DIR, 'image2.png')   # Màn hình chính ban đầu
IMG_SCREEN2 = os.path.join(IMAGES_DIR, 'image3.png')   # Sidebar sau upload 2 file
IMG_SCREEN3 = os.path.join(IMAGES_DIR, 'image4.png')   # Đang phân tích
IMG_SCREEN4 = os.path.join(IMAGES_DIR, 'image5.png')   # Kết quả phân tích ĐẠT
IMG_REPORT1 = os.path.join(IMAGES_DIR, 'image6.png')   # Báo cáo PDF trang 1
IMG_REPORT2 = os.path.join(IMAGES_DIR, 'image7.png')   # Báo cáo PDF trang 2


def set_cell_background(cell, hex_color):
    """Đặt màu nền cho cell trong bảng"""
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_color)
    tcPr.append(shd)


def add_table_border(table):
    """Thêm đường viền cho bảng"""
    tbl = table._tbl
    tblPr = tbl.find(qn('w:tblPr'))
    if tblPr is None:
        tblPr = OxmlElement('w:tblPr')
        tbl.insert(0, tblPr)
    tblBorders = OxmlElement('w:tblBorders')
    for border_name in ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']:
        border = OxmlElement(f'w:{border_name}')
        border.set(qn('w:val'), 'single')
        border.set(qn('w:sz'), '4')
        border.set(qn('w:space'), '0')
        border.set(qn('w:color'), 'AAAAAA')
        tblBorders.append(border)
    tblPr.append(tblBorders)


def add_image_caption(doc, caption_text):
    """Thêm chú thích ảnh căn giữa, in nghiêng"""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(caption_text)
    run.italic = True
    run.font.size = Pt(10)
    run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)


def add_image_centered(doc, img_path, width_inches=5.5, caption=None):
    """Thêm ảnh căn giữa với caption"""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    run.add_picture(img_path, width=Inches(width_inches))
    if caption:
        add_image_caption(doc, caption)


def set_paragraph_spacing(para, before=None, after=None, line=None):
    """Set spacing cho paragraph"""
    pPr = para._p.get_or_add_pPr()
    spacing = pPr.find(qn('w:spacing'))
    if spacing is None:
        spacing = OxmlElement('w:spacing')
        pPr.append(spacing)
    if before is not None:
        spacing.set(qn('w:before'), str(int(before * 20)))  # twips
    if after is not None:
        spacing.set(qn('w:after'), str(int(after * 20)))


# ============================================================
# BẮT ĐẦU TẠO TÀI LIỆU
# ============================================================
print("Đang tạo tài liệu...")

# Dùng template gốc để kế thừa tất cả styles, header/footer, page setup
doc = Document(TEMPLATE_PATH)

# Xóa toàn bộ nội dung hiện có trong document body (trừ header/footer)
# Chúng ta sẽ xóa từng element
body = doc.element.body
# Xóa tất cả paragraphs và tables hiện tại
for child in list(body):
    if child.tag in [qn('w:p'), qn('w:tbl'), qn('w:sectPr')]:
        if child.tag != qn('w:sectPr'):
            body.remove(child)

# Hàm thêm paragraph trước sectPr (để đúng thứ tự)
def add_para_before_sectpr(doc, text='', style='Normal'):
    """Thêm paragraph vào body trước sectPr"""
    p = doc.add_paragraph(text, style=style)
    return p

# ============================================================
# TRANG BÌA
# ============================================================

# Khoảng cách trên trang bìa
for _ in range(3):
    p = doc.add_paragraph()

# Logo CT Group
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run()
run.add_picture(IMG_LOGO, width=Inches(1.5))

doc.add_paragraph()

# Tiêu đề chính
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('AI ĐÁNH GIÁ HOÀN THÀNH THỬ VIỆC')
run.bold = True
run.font.size = Pt(22)
run.font.color.rgb = RGBColor(0x4C, 0x94, 0xD8)

# Tiêu đề phụ
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('TÀI LIỆU HƯỚNG DẪN SỬ DỤNG')
run.bold = True
run.font.size = Pt(16)
run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)

doc.add_paragraph()

# Bảng thông tin phiên bản
table = doc.add_table(rows=2, cols=4)
table.alignment = WD_TABLE_ALIGNMENT.CENTER
add_table_border(table)

headers = ['Phiên bản tài liệu', 'Người biên soạn', 'Người kiểm tra', 'Ngày cập nhật']
values  = ['1.0', 'Hồ Đắc Quân', 'Nguyễn Đức Cường', '01.6.2026']

for i, (h, v) in enumerate(zip(headers, values)):
    hcell = table.rows[0].cells[i]
    hcell.text = h
    hcell.paragraphs[0].runs[0].bold = True
    hcell.paragraphs[0].runs[0].font.size = Pt(10)
    set_cell_background(hcell, 'E8F4FD')
    
    vcell = table.rows[1].cells[i]
    vcell.text = v
    vcell.paragraphs[0].runs[0].font.size = Pt(10)

doc.add_paragraph()

# Thông tin tổ chức
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('Ban DAIT · CT Group · 2026')
run.font.size = Pt(11)
run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)

# Page break sau trang bìa
doc.add_page_break()

# ============================================================
# CHƯƠNG 1: GIỚI THIỆU HỆ THỐNG
# ============================================================
doc.add_heading('GIỚI THIỆU HỆ THỐNG', level=1)

doc.add_heading('1.1 Mục tiêu hệ thống', level=2)

p = doc.add_paragraph(
    'Hệ thống AI Đánh Giá Thử Việc là nền tảng ứng dụng Trí tuệ Nhân tạo để tự động hóa và nâng cao chất lượng quy trình kiểm tra, xác thực hồ sơ hoàn thành thử việc nhân sự tại CT Group.'
)

p = doc.add_paragraph('Hệ thống hướng tới 3 mục tiêu cốt lõi sau:')

p = doc.add_paragraph()
run = p.add_run('Mục tiêu 1: Tự động hóa kiểm tra và xác thực hồ sơ thử việc')
run.bold = True

doc.add_paragraph(
    '- Phát hiện thiếu sót tự động: Tự động phát hiện mục thiếu, số liệu không hợp lệ, link minh chứng trống và công thức tính KPI sai. Đưa ra hướng dẫn cụ thể cần sửa ở file nào, mục nào.'
)

p = doc.add_paragraph()
run = p.add_run('Mục tiêu 2: Đảm bảo Tính nhất quán và Chuẩn hóa hồ sơ')
run.bold = True

doc.add_paragraph(
    '- Đối chiếu chéo dữ liệu: Kiểm tra tỷ lệ KPI tuần, điểm trung bình 8 tuần, kết quả thực tế giữa file Word và file Excel có khớp nhau không.'
)
doc.add_paragraph(
    '- So sánh phiên bản: Khi user upload lại file đã chỉnh, AI tự động so sánh với lần trước và chỉ kiểm tra lại phần đã thay đổi.'
)
doc.add_paragraph(
    '- Phát hiện mâu thuẫn nội dung: Tự động đối chiếu phần mô tả nhiệm vụ trong Word với kết quả thực hiện trong bảng KPI Excel, cảnh báo khi có sự không nhất quán.'
)

p = doc.add_paragraph()
run = p.add_run('Mục tiêu 3: Tối ưu hóa thời gian và nguồn lực cho bộ phận C&B')
run.bold = True

doc.add_paragraph(
    '- Tiết kiệm thời gian C&B: Thay thế 60-80% thời gian đọc và soát xét hồ sơ thủ công, giúp C&B tập trung vào quyết định thay vì đọc từng dòng tài liệu.'
)
doc.add_paragraph(
    '- Xuất báo cáo PDF tự động: Tạo báo cáo kiểm tra định dạng A4 chuẩn ngay trong hệ thống, sẵn sàng lưu trữ hoặc trình cấp trên phê duyệt.'
)

doc.add_heading('1.2 Đối tượng sử dụng', level=2)

doc.add_paragraph(
    'Hệ thống được thiết kế phục vụ chính cho bộ phận C&B và các nhóm liên quan trong quy trình đánh giá thử việc:'
)

p = doc.add_paragraph()
run = p.add_run('C&B (Bộ phận đãi ngộ & phúc lợi):')
run.bold = True

doc.add_paragraph('- Mục đích sử dụng: Tiếp nhận, kiểm tra và xác thực hồ sơ hoàn thành thử việc từ các phòng ban trước khi trình Ban Giám đốc quyết định.')
doc.add_paragraph('- Giá trị mang lại: Không cần đọc thủ công toàn bộ hồ sơ. AI phát hiện tự động mọi thiếu sót, C&B chỉ cần review kết quả và xác nhận hoặc yêu cầu bổ sung.')

p = doc.add_paragraph()
run = p.add_run('Nhân sự thử việc:')
run.bold = True

doc.add_paragraph('- Mục đích sử dụng: Điền phiếu đánh giá Word và bảng KPI Excel theo đúng mẫu, sau đó gửi về C&B để kiểm tra.')
doc.add_paragraph('- Giá trị mang lại: Được hướng dẫn cụ thể cần bổ sung gì, sửa ở đâu khi hồ sơ chưa đạt – giảm vòng lặp email qua lại với C&B.')

p = doc.add_paragraph()
run = p.add_run('Ban Giám đốc (Người phê duyệt cuối):')
run.bold = True

doc.add_paragraph('- Mục đích sử dụng: Nhận báo cáo PDF tóm tắt kết quả kiểm tra AI trước khi ký phê duyệt hồ sơ thử việc.')
doc.add_paragraph('- Giá trị mang lại: Không cần đọc toàn bộ hồ sơ chi tiết. Chỉ cần xem báo cáo tóm tắt từ AI để ra quyết định phê duyệt hoặc yêu cầu bổ sung.')

doc.add_heading('1.3 Phạm vi chức năng', level=2)

doc.add_paragraph('Phạm vi hệ thống giới hạn trong các nghiệp vụ kiểm tra và xác thực hồ sơ thử việc:')
doc.add_paragraph('- Về loại hình dữ liệu: Hỗ trợ đọc và phân tích file Word (.docx) – Phiếu đánh giá thử việc, và file Excel (.xlsx) – Bảng Kế hoạch SXKD / KPI tháng.')
doc.add_paragraph('- Về quy trình áp dụng: Ứng dụng trong giai đoạn kiểm tra trước khi C&B trình hồ sơ lên cấp phê duyệt.')
doc.add_paragraph('- Về ranh giới hệ thống: AI chỉ kiểm tra và đưa ra gợi ý. Hệ thống không tự động sửa file gốc, không tự ra quyết định duyệt hay từ chối nhân sự, không lưu trữ dữ liệu sau phiên kết thúc.')

p = doc.add_paragraph()
run = p.add_run('Các chức năng chính: Kiểm tra và Xác thực Hồ sơ Thử việc')
run.bold = True

doc.add_paragraph('- Trích xuất và Phân tích Dữ liệu: Tự động bóc tách toàn bộ nội dung văn bản, bảng biểu từ file Word và Excel, chuyển thành dữ liệu có cấu trúc phục vụ phân tích AI.')
doc.add_paragraph('- Kiểm tra Phiếu đánh giá Word (5 phần): Phần I – Thông tin/câu hỏi; Phần II – Nhiệm vụ đã thực hiện (8 tuần); Phần III – Hội nhập; Phần IV – Người giao việc; Phần V – Tổng hợp.')
doc.add_paragraph('- Kiểm tra Bảng KPI Excel: Xác thực tỷ lệ thực hiện từng KPI (1.1→1.9), link minh chứng, phát hiện công thức tính điểm trung bình sai, đối chiếu với phần mô tả trong Word.')

# Bảng chức năng
p = doc.add_paragraph()
run = p.add_run('Bảng 1: Chức năng kiểm tra hồ sơ của hệ thống DAIT')
run.bold = True
run.font.size = Pt(10)
run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)

table = doc.add_table(rows=4, cols=2)
table.alignment = WD_TABLE_ALIGNMENT.CENTER
add_table_border(table)

# Header row
hrow = table.rows[0]
hrow.cells[0].text = 'Chức năng'
hrow.cells[1].text = 'Mô tả'
for cell in hrow.cells:
    cell.paragraphs[0].runs[0].bold = True
    cell.paragraphs[0].runs[0].font.size = Pt(10)
    set_cell_background(cell, 'E8F4FD')

# Data rows
data = [
    ('Kiểm tra Phiếu đánh giá Word', 'Phân tích 5 phần (I-V) của Phiếu đánh giá thử việc'),
    ('Kiểm tra Bảng KPI Excel', 'Xác thực KPI 1.1→1.9, link minh chứng, công thức trung bình 8 tuần'),
    ('So sánh phiên bản & Chat', 'So sánh file đã chỉnh với phiên bản trước + Chat hỏi thêm + Xuất PDF'),
]
for i, (func, desc) in enumerate(data):
    row = table.rows[i+1]
    row.cells[0].text = func
    row.cells[1].text = desc
    for cell in row.cells:
        if cell.paragraphs[0].runs:
            cell.paragraphs[0].runs[0].font.size = Pt(10)

doc.add_paragraph('- So sánh phiên bản: Khi upload lại file đã chỉnh, AI tự động so sánh với phiên bản trước và chỉ tập trung kiểm tra những gì đã thay đổi.')

doc.add_heading('1.4 Đường dẫn dự án', level=2)
doc.add_paragraph('http://localhost:5200/assets/ai_ats/frontend/')

# ============================================================
# CHƯƠNG 2: PHÂN QUYỀN HỆ THỐNG
# ============================================================
doc.add_page_break()
doc.add_heading('PHÂN QUYỀN HỆ THỐNG', level=1)

# Bảng phân quyền
table2 = doc.add_table(rows=3, cols=2)
table2.alignment = WD_TABLE_ALIGNMENT.CENTER
add_table_border(table2)

hrow2 = table2.rows[0]
hrow2.cells[0].text = 'Vai trò'
hrow2.cells[1].text = 'Quyền hạn chính'
for cell in hrow2.cells:
    cell.paragraphs[0].runs[0].bold = True
    cell.paragraphs[0].runs[0].font.size = Pt(10)
    set_cell_background(cell, 'E8F4FD')

roles_data = [
    ('Nhân sự thử việc', 'Upload Word + Excel, xem kết quả AI, xuất báo cáo PDF, điền phiếu đánh giá, upload lại file đã chỉnh'),
    ('Ban Giám đốc', 'Nhận báo cáo PDF tóm tắt, ra quyết định phê duyệt hoặc yêu cầu bổ sung'),
]
for i, (role, perm) in enumerate(roles_data):
    row = table2.rows[i+1]
    row.cells[0].text = role
    row.cells[1].text = perm
    for cell in row.cells:
        if cell.paragraphs[0].runs:
            cell.paragraphs[0].runs[0].font.size = Pt(10)

# ============================================================
# CHƯƠNG 3: HƯỚNG DẪN SỬ DỤNG CHI TIẾT
# ============================================================
doc.add_page_break()
doc.add_heading('HƯỚNG DẪN SỬ DỤNG CHI TIẾT', level=1)

doc.add_heading('3.1 Đăng nhập và khởi tạo', level=2)

p = doc.add_paragraph()
run = p.add_run('Bước 1:')
run.bold = True
p.add_run(' Truy cập hệ thống qua đường dẫn nội bộ được cấp')

p = doc.add_paragraph()
run = p.add_run('Bước 2:')
run.bold = True
p.add_run(' Đăng nhập bằng tài khoản nội bộ.')

doc.add_paragraph('Hệ thống sẽ tự động:')
doc.add_paragraph('- Xác thực tài khoản và phân quyền người dùng')
doc.add_paragraph('- Hiển thị màn hình chính với ô upload file bên trái và khu vực kết quả ở giữa')
doc.add_paragraph('- Khởi tạo Session ID bảo mật cho phiên làm việc')

doc.add_paragraph()
add_image_centered(doc, IMG_SCREEN1, width_inches=5.8,
                   caption='Ảnh 1: Màn hình giao diện chính – AI Đánh Giá Thử Việc')

p = doc.add_paragraph()
run = p.add_run('Bước 3:')
run.bold = True
p.add_run(' Upload file Phiếu đánh giá (Word .docx) và Bảng KPI (Excel .xlsx)')

doc.add_paragraph()
add_image_centered(doc, IMG_SCREEN2, width_inches=5.8,
                   caption='Ảnh 2: Sidebar bên trái sau khi upload đủ 2 file')

p = doc.add_paragraph()
run = p.add_run('Bước 4:')
run.bold = True
p.add_run(' Nhấn nút "Phân tích ngay" và chờ kết quả (15-30 giây).')

doc.add_paragraph('- Sidebar trái: Ô upload Phiếu đánh giá + Bảng KPI + nút Phân tích ngay')
doc.add_paragraph('- Khu vực trung tâm: Màn hình kết quả phân tích AI')
doc.add_paragraph('- Ô chat bên dưới: Upload lại file đã chỉnh hoặc hỏi thêm về hồ sơ')
doc.add_paragraph('- Trạng thái phiên: Chưa có phiên / Phiên đang hoạt động (góc dưới sidebar)')
doc.add_paragraph('- Nút Xuất báo cáo PDF: Hiển thị sau khi có kết quả phân tích')

doc.add_paragraph()
add_image_centered(doc, IMG_SCREEN3, width_inches=5.8,
                   caption='Ảnh 3: Màn hình đang phân tích hồ sơ')

# ============================================================
doc.add_heading('3.2 Thực hiện phân tích hồ sơ thử việc', level=2)

p = doc.add_paragraph()
run = p.add_run('Bước 1:')
run.bold = True
p.add_run(' Nhấn ô "Phiếu đánh giá" ở sidebar trái, chọn file .docx của nhân viên cần kiểm tra.')

doc.add_paragraph('Tên file mẫu: DAIT_Đánh giá hoàn thành thử việc_[Tên NV]_[Năm]_[Phiên bản].docx')

p = doc.add_paragraph()
run = p.add_run('Bước 2:')
run.bold = True
p.add_run(' Nhấn ô "Bảng KPI", chọn file .xlsx tương ứng của nhân viên đó.')

doc.add_paragraph('Tên file mẫu: ISO-MẪU-KẾ HOẠCH SXKD THÁNG VÀ BÁO CÁO KẾT QUẢ THỰC HIỆN.xlsx')

# ============================================================
doc.add_heading('3.3 Đọc kết quả đánh giá', level=2)

doc.add_paragraph('Sau khi AI xử lý xong, hệ thống trả về đầy đủ các thông tin sau:')
doc.add_paragraph('- Trạng thái tổng thể: ĐẠT (màu xanh) hoặc CHƯA ĐẠT – CẦN BỔ SUNG (màu cam), kèm nhận xét tổng quan từ AI.')
doc.add_paragraph('- Danh sách vấn đề cần bổ sung: Ghi rõ thuộc file nào (Word/Excel), mục nào, vấn đề gì, và cần làm gì để sửa.')
doc.add_paragraph('- Bảng KPI chi tiết: Từng mục KPI với tỷ lệ thực hiện, trạng thái (ĐẠT / THIẾU / CẢNH BÁO) và link minh chứng.')
doc.add_paragraph('- Điểm mạnh (ưu điểm): Những mục AI nhận thấy đã được điền đầy đủ và chính xác.')
doc.add_paragraph('- Bảng KPI tuần (1.1→1.9): Kết quả từng tuần và kiểm tra công thức tính trung bình.')

doc.add_paragraph(
    'Sau khi xem kết quả, nhấn nút "Xuất báo cáo PDF" ở sidebar trái để xuất báo cáo định dạng A4, sẵn sàng lưu trữ hoặc trình Ban Giám đốc phê duyệt.'
)

doc.add_paragraph()
add_image_centered(doc, IMG_SCREEN4, width_inches=5.8,
                   caption='Ảnh 4: Kết quả phân tích AI – Hồ sơ đạt yêu cầu với bảng KPI và điểm tốt')

# ============================================================
doc.add_heading('3.4 Bổ sung, Kiểm tra lại & Tiện ích mở rộng', level=2)

doc.add_paragraph(
    'Bên cạnh các tính năng kiểm tra hồ sơ, hệ thống cung cấp các công cụ hỗ trợ để C&B tối ưu hóa quy trình làm việc.'
)

p = doc.add_paragraph()
run = p.add_run('Bổ sung & Kiểm tra lại hồ sơ:')
run.bold = True

doc.add_paragraph('- Gửi danh sách vấn đề AI nêu ra cho HOD để chỉnh sửa đúng trọng tâm.')
doc.add_paragraph('- Upload lại file đã chỉnh: Nhấn biểu tượng 📎 ở ô chat, chọn "Word mới" hoặc "Excel mới", thêm ghi chú nếu cần, nhấn gửi.')

# ============================================================
doc.add_heading('3.5 Kết quả kiểm tra mẫu thực tế', level=2)

doc.add_paragraph(
    'Dưới đây là báo cáo AI tự động xuất ra sau khi C&B upload đủ 2 file (Phiếu đánh giá Word + Bảng KPI Excel) của nhân viên Hồ Đắc Quân – dùng làm mẫu minh họa quy trình kiểm tra thực tế trên hệ thống.'
)

doc.add_paragraph()
add_image_centered(doc, IMG_REPORT1, width_inches=5.8,
                   caption='Ảnh 7: Báo cáo AI – Trang 1/2 (Thông tin nhân viên, HOD, nhận xét tổng quan và kết quả từng phần)')

doc.add_paragraph()
add_image_centered(doc, IMG_REPORT2, width_inches=5.8,
                   caption='Ảnh 8: Báo cáo AI – Trang 2/2 (Hội nhập, người giao việc, điểm tốt và bảng KPI chi tiết)')

# ============================================================
# LƯU FILE
# ============================================================
doc.save(OUTPUT_PATH)
print(f"\n✅ Tài liệu đã được tạo thành công!")
print(f"   → {OUTPUT_PATH}")
