import flet as ft
import os
import io
import zipfile
import struct
import math
import hashlib
import random
import tempfile
import logging
from pathlib import Path
from typing import Optional, Tuple, Union, List

from PIL import Image


# ============================================================
# U92 CONSTANTS
# ============================================================

MAGIC_BYTES = b"U92ARCHV"
HEADER_SIZE = 16
HEADER_BITS = HEADER_SIZE * 8
BITS_PER_BYTE = 8
CHANNELS = 3
DEFAULT_CAPACITY_BUFFER = 1.05


# ============================================================
# LOGGING
# ============================================================

def configure_logging(verbose=False):
    logger = logging.getLogger("U92_GUI")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    logger.handlers.clear()

    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG if verbose else logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


logger = configure_logging()


# ============================================================
# BIT UTILITIES
# ============================================================

def bytes_to_bits(data: bytes) -> List[int]:
    bits = []

    for byte in data:
        for shift in range(7, -1, -1):
            bits.append((byte >> shift) & 1)

    return bits


def bits_to_bytes(bits: List[int]) -> bytes:
    complete_bytes = len(bits) // 8
    result = bytearray(complete_bytes)

    for byte_index in range(complete_bytes):
        value = 0
        base = byte_index * 8

        for offset in range(8):
            value = (value << 1) | bits[base + offset]

        result[byte_index] = value

    return bytes(result)


# ============================================================
# CONTINUOUS BITSTREAM READER
# ============================================================

class ContinuousBitStreamReader:

    def __init__(self, image: Image.Image):

        self.width, self.height = image.size
        self.pixels = image.load()

        self.total_pixels = self.width * self.height
        self.pixel_index = 0

        self.buffer = []
        self.bits_read = 0

    def _read_next_pixel_bits(self):

        if self.pixel_index >= self.total_pixels:
            return

        x = self.pixel_index % self.width
        y = self.pixel_index // self.width

        self.pixel_index += 1

        pixel = self.pixels[x, y]

        if isinstance(pixel, (tuple, list)):
            r = pixel[0]
            g = pixel[1]
            b = pixel[2]
        else:
            r = g = b = int(pixel)

        self.buffer.append(r & 1)
        self.buffer.append(g & 1)
        self.buffer.append(b & 1)

    def read_bits(self, count):

        if count < 0:
            raise ValueError("Cannot read negative bits.")

        if count == 0:
            return []

        while (
            len(self.buffer) < count
            and self.pixel_index < self.total_pixels
        ):
            self._read_next_pixel_bits()

        available = min(count, len(self.buffer))

        result = self.buffer[:available]

        self.buffer = self.buffer[available:]

        self.bits_read += available

        return result


# ============================================================
# IMAGE UTILITIES
# ============================================================

def calculate_capacity(width, height):

    return (
        width
        * height
        * CHANNELS
    ) // BITS_PER_BYTE


def calculate_dimensions_for_payload(payload_size):

    required_bytes = int(
        payload_size * DEFAULT_CAPACITY_BUFFER
    )

    required_bits = required_bytes * 8

    required_pixels = math.ceil(
        required_bits / CHANNELS
    )

    height = math.ceil(
        math.sqrt(required_pixels / 1.5)
    )

    width = math.ceil(
        required_pixels / height
    )

    width = max(width, 8)
    height = max(height, 8)

    return width, height


def normalize_pixel(pixel):

    if isinstance(pixel, (tuple, list)):

        return (
            int(pixel[0]),
            int(pixel[1]),
            int(pixel[2]),
        )

    value = int(pixel)

    return value, value, value


# ============================================================
# ARCHIVE
# ============================================================

def pack_folder(source_path):

    source = Path(source_path).resolve()

    if not source.exists():
        raise FileNotFoundError(
            f"Source does not exist:\n{source_path}"
        )

    buffer = io.BytesIO()

    with zipfile.ZipFile(
        buffer,
        "w",
        zipfile.ZIP_DEFLATED,
    ) as zipf:

        if source.is_file():

            zipf.write(
                source,
                source.name,
            )

        elif source.is_dir():

            for root, dirs, files in os.walk(source):

                root_path = Path(root)

                for file_name in files:

                    file_path = root_path / file_name

                    archive_name = str(
                        file_path.relative_to(
                            source.parent
                        )
                    )

                    zipf.write(
                        file_path,
                        archive_name,
                    )

                for directory in dirs:

                    directory_path = (
                        root_path / directory
                    )

                    if not any(
                        directory_path.iterdir()
                    ):

                        archive_name = (
                            str(
                                directory_path.relative_to(
                                    source.parent
                                )
                            )
                            + "/"
                        )

                        zipf.writestr(
                            archive_name,
                            "",
                        )

        else:

            raise ValueError(
                "Path is neither a file nor directory."
            )

    return buffer.getvalue()


# ============================================================
# SAFE EXTRACTION
# ============================================================

def validate_path_safety(
    base_path,
    target_path,
):

    try:

        base = Path(base_path).resolve()

        target = (
            base / target_path
        ).resolve()

        return target.is_relative_to(base)

    except Exception:

        return False


def unpack_archive(
    archive_bytes,
    destination,
):

    destination = Path(
        destination
    ).resolve()

    destination.mkdir(
        parents=True,
        exist_ok=True,
    )

    with zipfile.ZipFile(
        io.BytesIO(archive_bytes),
        "r",
    ) as zipf:

        for member in zipf.namelist():

            if not validate_path_safety(
                destination,
                member,
            ):

                raise ValueError(
                    "Unsafe archive path detected:\n"
                    + member
                )

        zipf.extractall(destination)


# ============================================================
# EMBED
# ============================================================

def embed_data(
    carrier_image_path,
    payload,
    output_path,
    auto_generate=False,
):

    header = (
        MAGIC_BYTES
        + struct.pack(
            "<Q",
            len(payload),
        )
    )

    complete_payload = (
        header + payload
    )

    total_size = len(
        complete_payload
    )

    if auto_generate:

        width, height = (
            calculate_dimensions_for_payload(
                total_size
            )
        )

        image = Image.new(
            "RGB",
            (width, height),
            (0, 0, 0),
        )

    else:

        if not carrier_image_path:

            raise ValueError(
                "Carrier image is required."
            )

        carrier = Path(
            carrier_image_path
        )

        if not carrier.exists():

            raise FileNotFoundError(
                "Carrier image not found:\n"
                + str(carrier)
            )

        image = Image.open(
            carrier
        ).convert("RGB")

    width, height = image.size

    capacity = calculate_capacity(
        width,
        height,
    )

    if total_size > capacity:

        raise ValueError(
            "Payload exceeds image capacity.\n\n"
            f"Required: {total_size:,} bytes\n"
            f"Available: {capacity:,} bytes"
        )

    payload_bits = bytes_to_bits(
        complete_payload
    )

    output = Image.new(
        "RGB",
        (width, height),
    )

    source_pixels = image.load()
    output_pixels = output.load()

    bit_index = 0

    for y in range(height):

        for x in range(width):

            r, g, b = normalize_pixel(
                source_pixels[x, y]
            )

            if bit_index < len(payload_bits):

                r = (
                    r & 0xFE
                ) | payload_bits[bit_index]

                bit_index += 1

            if bit_index < len(payload_bits):

                g = (
                    g & 0xFE
                ) | payload_bits[bit_index]

                bit_index += 1

            if bit_index < len(payload_bits):

                b = (
                    b & 0xFE
                ) | payload_bits[bit_index]

                bit_index += 1

            output_pixels[x, y] = (
                r,
                g,
                b,
            )

    if bit_index != len(payload_bits):

        raise ValueError(
            "Embedding did not complete."
        )

    output_path = Path(
        output_path
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.save(
        output_path,
        "PNG",
    )

    return {
        "width": width,
        "height": height,
        "capacity": capacity,
        "payload_size": len(payload),
        "total_size": total_size,
        "usage": (
            total_size / capacity
        ) * 100,
    }


# ============================================================
# EXTRACT
# ============================================================

def extract_data(
    stego_image_path,
):

    stego_path = Path(
        stego_image_path
    )

    if not stego_path.exists():

        raise FileNotFoundError(
            "Stego image not found."
        )

    image = Image.open(
        stego_path
    ).convert("RGB")

    width, height = image.size

    reader = ContinuousBitStreamReader(
        image
    )

    header_bits = reader.read_bits(
        HEADER_BITS
    )

    if len(header_bits) != HEADER_BITS:

        raise ValueError(
            "Image is too small for a U92 header."
        )

    header = bits_to_bytes(
        header_bits
    )

    magic = header[:8]

    if magic != MAGIC_BYTES:

        raise ValueError(
            "No valid U92 archive found in this image."
        )

    payload_size = struct.unpack(
        "<Q",
        header[8:16],
    )[0]

    max_payload = (
        calculate_capacity(
            width,
            height,
        )
        - HEADER_SIZE
    )

    if payload_size > max_payload:

        raise ValueError(
            "Invalid payload size stored in image."
        )

    payload_bits = reader.read_bits(
        payload_size * 8
    )

    if len(payload_bits) != (
        payload_size * 8
    ):

        raise ValueError(
            "Embedded payload is incomplete."
        )

    payload = bits_to_bytes(
        payload_bits
    )

    if len(payload) != payload_size:

        raise ValueError(
            "Payload size verification failed."
        )

    return payload


# ============================================================
# ZIP VALIDATION
# ============================================================

def validate_zip(payload):

    with zipfile.ZipFile(
        io.BytesIO(payload),
        "r",
    ) as archive:

        bad = archive.testzip()

        if bad:

            raise zipfile.BadZipFile(
                f"Corrupted archive member: {bad}"
            )


# ============================================================
# ROUND TRIP TEST
# ============================================================

def verify_round_trip():

    test_data = bytes(
        random.Random(42).getrandbits(8)
        for _ in range(1024)
    )

    with tempfile.NamedTemporaryFile(
        suffix=".png",
        delete=False,
    ) as temp:

        temp_path = temp.name

    try:

        embed_data(
            None,
            test_data,
            temp_path,
            True,
        )

        extracted = extract_data(
            temp_path
        )

        return (
            test_data == extracted
            and hashlib.sha256(
                test_data
            ).digest()
            == hashlib.sha256(
                extracted
            ).digest()
        )

    finally:

        try:
            os.remove(temp_path)
        except OSError:
            pass


# ============================================================
# GUI
# ============================================================

def main(page: ft.Page):

    page.title = "U92 PRO Steganography"
    page.padding = 0

    # Window icon
    try:
        icon_path = Path(__file__).parent / "assets" / "u92.ico"
        page.window.icon = str(icon_path)
    except Exception:
        pass
    
    page.bgcolor = "#080A0F"

    page.window_min_width = 900
    page.window_min_height = 650

    # --------------------------------------------------------
    # STATE
    # --------------------------------------------------------

    active_page = "dashboard"

    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    status_text = ft.Text(
        "Ready",
        size=13,
        color="#8B93A7",
    )

    result_text = ft.Text(
        "",
        size=13,
        color="#C7CDDA",
    )

    progress = ft.ProgressBar(
        value=0,
        visible=False,
    )

    # --------------------------------------------------------
    # INPUTS
    # --------------------------------------------------------

    source_field = ft.TextField(
        label="Source file / folder",
        hint_text="C:\\Users\\You\\Documents\\secret",
        expand=True,
        dense=True,
    )

    carrier_field = ft.TextField(
        label="Carrier PNG (optional in Auto mode)",
        hint_text="C:\\Images\\carrier.png",
        expand=True,
        dense=True,
    )

    output_field = ft.TextField(
        label="Output PNG",
        hint_text="C:\\Images\\u92_output.png",
        expand=True,
        dense=True,
    )

    stego_field = ft.TextField(
        label="Stego PNG",
        hint_text="C:\\Images\\u92_output.png",
        expand=True,
        dense=True,
    )

    destination_field = ft.TextField(
        label="Extraction destination",
        hint_text="C:\\Users\\You\\Desktop\\Recovered",
        expand=True,
        dense=True,
    )

    # --------------------------------------------------------
    # MODE SWITCH
    # --------------------------------------------------------

    auto_switch = ft.Switch(
        label="Auto-generate carrier",
        value=True,
    )

    # --------------------------------------------------------
    # HELPERS
    # --------------------------------------------------------

    def set_status(
        message,
        color="#8B93A7",
    ):

        status_text.value = message
        status_text.color = color
        page.update()

    def show_error(error):

        set_status(
            str(error),
            "#FF6B6B",
        )

        result_text.value = (
            "Operation failed.\n\n"
            + str(error)
        )

        result_text.color = "#FF7A7A"

        page.update()

    def show_success(message):

        set_status(
            "Operation completed successfully",
            "#63E6BE",
        )

        result_text.value = message
        result_text.color = "#63E6BE"

        page.update()

    def run_embed(e):

        progress.visible = True
        progress.value = None

        set_status(
            "Preparing archive...",
            "#8AB4FF",
        )

        page.update()

        try:

            source = (
                source_field.value or ""
            ).strip()

            carrier = (
                carrier_field.value or ""
            ).strip()

            output = (
                output_field.value or ""
            ).strip()

            if not source:

                raise ValueError(
                    "Enter a source file or folder."
                )

            if not output:

                raise ValueError(
                    "Enter an output PNG path."
                )

            if not output.lower().endswith(
                ".png"
            ):

                output += ".png"

            if (
                not auto_switch.value
                and not carrier
            ):

                raise ValueError(
                    "Enter a carrier PNG or enable Auto-generate."
                )

            set_status(
                "Compressing source...",
                "#8AB4FF",
            )

            page.update()

            archive = pack_folder(
                source
            )

            set_status(
                "Embedding data into PNG...",
                "#8AB4FF",
            )

            page.update()

            stats = embed_data(
                carrier_image_path=carrier
                if not auto_switch.value
                else None,
                payload=archive,
                output_path=output,
                auto_generate=auto_switch.value,
            )

            show_success(
                "U92 EMBEDDING COMPLETE\n\n"
                f"Source archive: {len(archive):,} bytes\n"
                f"Total embedded: {stats['total_size']:,} bytes\n"
                f"Image: {stats['width']} × {stats['height']}\n"
                f"Capacity: {stats['capacity']:,} bytes\n"
                f"Capacity used: {stats['usage']:.2f}%\n\n"
                f"Output:\n{output}"
            )

        except Exception as error:

            show_error(error)

        finally:

            progress.visible = False
            progress.value = 0
            page.update()

    def run_extract(e):

        progress.visible = True
        progress.value = None

        set_status(
            "Extracting U92 payload...",
            "#8AB4FF",
        )

        page.update()

        try:

            stego = (
                stego_field.value or ""
            ).strip()

            destination = (
                destination_field.value or ""
            ).strip()

            if not stego:

                raise ValueError(
                    "Enter the stego PNG path."
                )

            if not destination:

                raise ValueError(
                    "Enter an extraction destination."
                )

            payload = extract_data(
                stego
            )

            set_status(
                "Verifying ZIP integrity...",
                "#8AB4FF",
            )

            page.update()

            validate_zip(payload)

            unpack_archive(
                payload,
                destination,
            )

            show_success(
                "U92 EXTRACTION COMPLETE\n\n"
                f"Payload: {len(payload):,} bytes\n\n"
                f"Recovered to:\n{destination}"
            )

        except Exception as error:

            show_error(error)

        finally:

            progress.visible = False
            progress.value = 0
            page.update()

    def run_test(e):

        progress.visible = True
        progress.value = None

        set_status(
            "Running integrity test...",
            "#8AB4FF",
        )

        page.update()

        try:

            success = verify_round_trip()

            if success:

                show_success(
                    "INTEGRITY TEST PASSED\n\n"
                    "Continuous bitstream round-trip "
                    "verified successfully.\n\n"
                    "SHA-256 comparison matched."
                )

            else:

                raise ValueError(
                    "Round-trip verification failed."
                )

        except Exception as error:

            show_error(error)

        finally:

            progress.visible = False
            progress.value = 0
            page.update()

    # --------------------------------------------------------
    # UI COMPONENTS
    # --------------------------------------------------------

    def card(content):

        return ft.Container(
            content=content,
            padding=20,
            border_radius=16,
            bgcolor="#10141D",
            border=ft.Border(
                top=ft.BorderSide(1, "#202735"),
                bottom=ft.BorderSide(1, "#202735"),
                left=ft.BorderSide(1, "#202735"),
                right=ft.BorderSide(1, "#202735"),
            ),
        )

    def action_button(
        label,
        icon,
        callback,
        primary=False,
    ):

        return ft.Button(
            content=ft.Row(
                controls=[
                    ft.Icon(
                        icon,
                        size=18,
                    ),
                    ft.Text(
                        label,
                        size=14,
                        weight=ft.FontWeight.W_600,
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=8,
            ),
            on_click=callback,
            height=48,
            expand=True,
            bgcolor=(
                "#2563EB"
                if primary
                else "#171D28"
            ),
            color="#FFFFFF",
        )

    # --------------------------------------------------------
    # DASHBOARD
    # --------------------------------------------------------

    def dashboard_view():

        return ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            controls=[

                ft.Text(
                    "U92 Steganography",
                    size=30,
                    weight=ft.FontWeight.W_700,
                    color="#F4F7FB",
                ),

                ft.Text(
                    "Continuous Bitstream Engine v2.3",
                    size=14,
                    color="#7F899C",
                ),

                ft.Container(
                    height=18,
                ),

                ft.Row(
                    controls=[
                        card(
                            ft.Column(
                                controls=[
                                    ft.Icon(
                                        ft.Icons.SECURITY,
                                        size=30,
                                        color="#60A5FA",
                                    ),
                                    ft.Text(
                                        "LSB Steganography",
                                        size=17,
                                        weight=ft.FontWeight.W_600,
                                    ),
                                    ft.Text(
                                        "Hide files and folders inside PNG images.",
                                        color="#7F899C",
                                    ),
                                ],
                                spacing=8,
                            )
                        ),

                        card(
                            ft.Column(
                                controls=[
                                    ft.Icon(
                                        ft.Icons.FOLDER_ZIP,
                                        size=30,
                                        color="#A78BFA",
                                    ),
                                    ft.Text(
                                        "ZIP Packaging",
                                        size=17,
                                        weight=ft.FontWeight.W_600,
                                    ),
                                    ft.Text(
                                        "Data is compressed before embedding.",
                                        color="#7F899C",
                                    ),
                                ],
                                spacing=8,
                            )
                        ),

                        card(
                            ft.Column(
                                controls=[
                                    ft.Icon(
                                        ft.Icons.VERIFIED,
                                        size=30,
                                        color="#34D399",
                                    ),
                                    ft.Text(
                                        "Integrity",
                                        size=17,
                                        weight=ft.FontWeight.W_600,
                                    ),
                                    ft.Text(
                                        "Continuous bitstream round-trip verification.",
                                        color="#7F899C",
                                    ),
                                ],
                                spacing=8,
                            )
                        ),
                    ],
                    spacing=14,
                ),

                ft.Container(
                    height=20,
                ),

                card(
                    ft.Column(
                        controls=[
                            ft.Text(
                                "Quick Actions",
                                size=19,
                                weight=ft.FontWeight.W_600,
                            ),

                            ft.Container(
                                height=6,
                            ),

                            ft.Row(
                                controls=[
                                    action_button(
                                        "Embed Data",
                                        ft.Icons.LOCK,
                                        lambda e: show_page(
                                            "embed"
                                        ),
                                        True,
                                    ),
                                    action_button(
                                        "Extract Data",
                                        ft.Icons.LOCK_OPEN,
                                        lambda e: show_page(
                                            "extract"
                                        ),
                                    ),
                                    action_button(
                                        "Integrity Test",
                                        ft.Icons.VERIFIED,
                                        run_test,
                                    ),
                                ],
                                spacing=12,
                            ),
                        ],
                    )
                ),

                ft.Container(
                    height=20,
                ),

                card(
                    ft.Column(
                        controls=[
                            ft.Text(
                                "Operation Status",
                                size=18,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.Container(
                                height=8,
                            ),
                            status_text,
                            progress,
                            result_text,
                        ],
                        spacing=8,
                    )
                ),
            ],
        )

    # --------------------------------------------------------
    # EMBED PAGE
    # --------------------------------------------------------

    def embed_view():

        return ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            controls=[

                ft.Text(
                    "Embed Data",
                    size=28,
                    weight=ft.FontWeight.W_700,
                ),

                ft.Text(
                    "Compress a file or folder and hide it inside a PNG.",
                    color="#7F899C",
                ),

                ft.Container(
                    height=16,
                ),

                card(
                    ft.Column(
                        controls=[

                            source_field,

                            ft.Container(
                                height=4,
                            ),

                            ft.Text(
                                "Carrier",
                                size=14,
                                weight=ft.FontWeight.W_600,
                            ),

                            auto_switch,

                            carrier_field,

                            ft.Container(
                                height=4,
                            ),

                            output_field,

                            ft.Container(
                                height=8,
                            ),

                            action_button(
                                "Start Embedding",
                                ft.Icons.LOCK,
                                run_embed,
                                True,
                            ),
                        ],
                        spacing=10,
                    )
                ),

                ft.Container(
                    height=16,
                ),

                card(
                    ft.Column(
                        controls=[
                            ft.Text(
                                "How it works",
                                size=17,
                                weight=ft.FontWeight.W_600,
                            ),

                            ft.Text(
                                "1. Source is compressed into ZIP.\n"
                                "2. U92 header is added.\n"
                                "3. Data is converted into a continuous bitstream.\n"
                                "4. Bits are stored in RGB least-significant bits.\n"
                                "5. The final image is saved as lossless PNG.",
                                color="#8B93A7",
                            ),
                        ],
                        spacing=8,
                    )
                ),
            ],
        )

    # --------------------------------------------------------
    # EXTRACT PAGE
    # --------------------------------------------------------

    def extract_view():

        return ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            controls=[

                ft.Text(
                    "Extract Data",
                    size=28,
                    weight=ft.FontWeight.W_700,
                ),

                ft.Text(
                    "Recover the hidden files from a U92 PNG.",
                    color="#7F899C",
                ),

                ft.Container(
                    height=16,
                ),

                card(
                    ft.Column(
                        controls=[

                            stego_field,

                            destination_field,

                            ft.Container(
                                height=8,
                            ),

                            action_button(
                                "Extract & Recover",
                                ft.Icons.LOCK_OPEN,
                                run_extract,
                                True,
                            ),
                        ],
                        spacing=12,
                    )
                ),

                ft.Container(
                    height=16,
                ),

                card(
                    ft.Column(
                        controls=[
                            ft.Text(
                                "Security",
                                size=17,
                                weight=ft.FontWeight.W_600,
                            ),

                            ft.Text(
                                "The archive is checked before extraction "
                                "and archive paths are validated against "
                                "path traversal.",
                                color="#8B93A7",
                            ),
                        ],
                        spacing=8,
                    )
                ),
            ],
        )

    # --------------------------------------------------------
    # PAGE SWITCHING
    # --------------------------------------------------------

    content_area = ft.Container(
        expand=True,
        padding=24,
    )

    def show_page(name):

        nonlocal active_page

        active_page = name

        if name == "dashboard":

            content_area.content = (
                dashboard_view()
            )

        elif name == "embed":

            content_area.content = (
                embed_view()
            )

        elif name == "extract":

            content_area.content = (
                extract_view()
            )

        page.update()

    # --------------------------------------------------------
    # SIDEBAR
    # --------------------------------------------------------

    def nav_button(
        key,
        label,
        icon,
        callback,
    ):

        return ft.Button(
            content=ft.Row(
                controls=[
                    ft.Icon(
                        icon,
                        size=19,
                    ),
                    ft.Text(
                        label,
                        size=14,
                    ),
                ],
                spacing=12,
            ),
            on_click=callback,
            bgcolor="#151B26",
            color="#DCE3F0",
            height=46,
        )

    sidebar = ft.Container(
        width=245,
        padding=18,
        bgcolor="#0D1118",
        border=ft.Border(
            right=ft.BorderSide(
                1,
                "#202735",
            )
        ),
        content=ft.Column(
            controls=[

                ft.Row(
                    controls=[
                        ft.Container(
                            width=42,
                            height=42,
                            bgcolor="#2563EB",
                            border_radius=12,
                            alignment=ft.Alignment.CENTER,
                            content=ft.Text(
                                "U92",
                                size=14,
                                weight=ft.FontWeight.W_700,
                            ),
                        ),

                        ft.Column(
                            controls=[
                                ft.Text(
                                    "U92",
                                    size=18,
                                    weight=ft.FontWeight.W_700,
                                ),
                                ft.Text(
                                    "STEGANOGRAPHY",
                                    size=9,
                                    color="#6F7A8D",
                                ),
                            ],
                            spacing=0,
                        ),
                    ],
                    spacing=10,
                ),

                ft.Container(
                    height=25,
                ),

                nav_button(
                    "dashboard",
                    "Dashboard",
                    ft.Icons.DASHBOARD,
                    lambda e: show_page(
                        "dashboard"
                    ),
                ),

                nav_button(
                    "embed",
                    "Embed Data",
                    ft.Icons.LOCK,
                    lambda e: show_page(
                        "embed"
                    ),
                ),

                nav_button(
                    "extract",
                    "Extract Data",
                    ft.Icons.LOCK_OPEN,
                    lambda e: show_page(
                        "extract"
                    ),
                ),

                ft.Container(
                    expand=True,
                ),

                ft.Divider(
                    height=1,
                    color="#202735",
                ),

                ft.Text(
                    "U92 Framework",
                    size=11,
                    color="#596477",
                ),

                ft.Text(
                    "Continuous Bitstream Engine",
                    size=10,
                    color="#454E5F",
                ),
            ],
            spacing=10,
        ),
    )

    # --------------------------------------------------------
    # MAIN LAYOUT
    # --------------------------------------------------------

    page.add(
        ft.Row(
            expand=True,
            spacing=0,
            controls=[
                sidebar,
                content_area,
            ],
        )
    )

    show_page("dashboard")


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    ft.run(main)