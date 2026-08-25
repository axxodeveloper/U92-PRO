# U92 PRO Steganography

### Continuous Bitstream Engine v2.3

U92 is a lightweight desktop steganography tool built with **Python, Flet, and Pillow**.

It compresses files or folders into a ZIP archive and embeds the data into the **LSB (Least Significant Bit)** of RGB pixels inside a PNG image.

<br>

> **Note:** U92 provides steganography, not encryption. The embedded data is not encrypted by default.You can password protect before uploading the zip file for more encryption

---

## Features

- LSB-based PNG steganography
- Hide files or entire folders
- ZIP compression before embedding
- Auto-generated carrier images
- Custom carrier image support
- Continuous bitstream processing
- Payload and header validation
- ZIP integrity verification
- Path traversal protection
- SHA-256 round-trip integrity test
- Dark-themed Flet desktop GUI
- Automatic capacity calculation

---

## How It Works

```text
File / Folder
     ↓
ZIP Compression
     ↓
U92 Header
     ↓
Bitstream
     ↓
RGB LSB Embedding
     ↓
PNG
```

Extraction reverses the process:

```text
U92 PNG
   ↓
Read LSB Bitstream
   ↓
Validate U92 Header
   ↓
Recover ZIP
   ↓
Verify Archive
   ↓
Extract Files
```

---

## Requirements

- Python 3.9+
- Flet
- Pillow

---

## Installation

```bash
git clone https://github.com/axxodeveloper/U92-PRO.git
cd U92-PRO

python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt
```

Or install the dependencies directly:

```bash
pip install flet pillow
```

---

## Run

```bash
python main.py
```

The application includes:

```text
Dashboard
├── Embed Data
├── Extract Data
└── Integrity Test
```

---

## Embedding

1. Open **Embed Data**
2. Select a file or folder
3. Enable **Auto-generate carrier** or provide your own image
4. Choose the output PNG
5. Start embedding

U92 automatically compresses the source and embeds it into the PNG.

---

## Extraction

1. Open **Extract Data**
2. Select a U92 PNG
3. Choose an extraction folder
4. Click **Extract & Recover**

The archive is verified and its paths are checked before extraction.

---

## Carrier Images

U92 can generate a carrier automatically or use an existing image.

The final stego image is always saved as **PNG** because PNG is lossless.

Avoid converting the resulting image to JPEG or resizing it, as modifying pixel data can corrupt the embedded payload.

---

## Integrity Test

U92 includes a built-in round-trip test:

```text
Generate Test Data
       ↓
     Embed
       ↓
    Extract
       ↓
 SHA-256 Compare
```

A successful test confirms that the embedded data can be recovered correctly.

---

## Project Structure

```text
U92-PRO/
│
├── main.py
├── requirements.txt
├── README.md
│
└── assets/
    └── u92.ico
```

---

## Security

U92 includes:

- U92 header validation
- Payload size validation
- ZIP integrity checking
- Safe archive extraction
- Path traversal protection

However, **U92 is not an encryption tool**.

For sensitive data, encrypt the data before embedding it.

---

## Limitations

- Payload size is limited by image dimensions
- Lossy image formats can corrupt embedded data
- Resizing or modifying a stego image may break extraction
- Steganography does not guarantee detection resistance
- No built-in encryption

---

## Tech Stack

**Python** • **Flet** • **Pillow** • **ZIP**

---

## Disclaimer

U92 is intended for legitimate **privacy, educational, research, archival, and authorized security-testing purposes**.

Use the software responsibly and only with data and systems you are authorized to work with.

---

## License

Add your preferred license here.

Example:

```text
MIT License
```

---

<div align="center">


**Compress. Embed. Verify. Recover.**

A lightweight continuous-bitstream steganography engine for PNG images.

<br>

**Made with love ❤ and Python**

**Axxo**

</div>
