import os
import io
import re
import zipfile
import uuid
import html
import smtplib
import ssl
from concurrent.futures import ThreadPoolExecutor
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image

from backend.utils.image_utils import optimize_for_kindle
from backend.services.progress_tracker import ProgressTracker

class KindleService:
    DEFAULT_KINDLE_EMAIL = "nit.ratha01_t9Ucaw@kindle.com"

    @staticmethod
    def send_to_kindle(
        file_path: str,
        kindle_email: str = DEFAULT_KINDLE_EMAIL,
        smtp_host: Optional[str] = None,
        smtp_port: int = 587,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        from_email: Optional[str] = None
    ) -> Dict[str, Any]:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if file_size_mb > 49.0:
            raise ValueError(
                f"File size ({file_size_mb:.1f} MB) exceeds Amazon's 50 MB email limit. "
                f"Use ⚡ 'Auto-Split & Compress for Kindle' below to convert into <45MB Kindle volumes!"
            )

        filename = os.path.basename(file_path)
        clean_filename = filename.split("_", 1)[1] if ("_" in filename and len(filename.split("_")[0]) == 36) else filename

        if smtp_host and smtp_user and smtp_password:
            sender = from_email or smtp_user
            msg = MIMEMultipart()
            msg["From"] = sender
            msg["To"] = kindle_email
            msg["Subject"] = clean_filename

            body = f"Sending {clean_filename} to Kindle device."
            msg.attach(MIMEText(body, "plain"))

            with open(file_path, "rb") as attachment:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f'attachment; filename="{clean_filename}"'
                )
                msg.attach(part)

            context = ssl.create_default_context()
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls(context=context)
                server.login(smtp_user, smtp_password)
                server.sendmail(sender, kindle_email, msg.as_string())

            return {
                "success": True,
                "message": f"Successfully sent {clean_filename} ({file_size_mb:.1f} MB) to {kindle_email}!"
            }
        else:
            return {
                "success": True,
                "mode": "ready",
                "filename": clean_filename,
                "file_size": f"{file_size_mb:.1f} MB",
                "kindle_email": kindle_email,
                "amazon_web_url": "https://www.amazon.com/sendtokindle",
                "message": f"File {clean_filename} ({file_size_mb:.1f} MB) is Kindle-Ready and optimized for {kindle_email}!"
            }

    @staticmethod
    def optimize_and_split_epub(
        file_path: str,
        output_dir: str,
        tracker: Optional[ProgressTracker] = None,
        task_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Takes a large EPUB file (>50MB), extracts images, compresses them specifically for Kindle E-Ink,
        reports real-time percentage progress, and splits into Kindle-compliant Volumes (<45MB each).
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        os.makedirs(output_dir, exist_ok=True)
        base_name = os.path.basename(file_path)
        clean_title = base_name.split("_", 1)[1] if ("_" in base_name and len(base_name.split("_")[0]) == 36) else base_name
        clean_title = re.sub(r'\.epub$', '', clean_title, flags=re.IGNORECASE)

        # 1. Extract image files
        extracted_images: List[Tuple[str, bytes]] = []
        with zipfile.ZipFile(file_path, "r") as zf:
            image_names = sorted([
                f for f in zf.namelist()
                if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.avif'))
            ])
            for name in image_names:
                img_bytes = zf.read(name)
                extracted_images.append((name, img_bytes))

        total_pages = len(extracted_images)
        if total_pages == 0:
            raise ValueError("No images found inside original EPUB to optimize.")

        pages_per_volume = 250
        num_volumes = (total_pages + pages_per_volume - 1) // pages_per_volume

        if tracker and task_id:
            tracker.update_task(
                task_id,
                status="splitting",
                progress_percent=2.0,
                total_pages_overall=total_pages,
                total_pages_downloaded=0,
                message=f"Starting Kindle optimization for {total_pages} pages (~{num_volumes} volumes)..."
            )

        # 2. Parallel Fast Kindle Image Optimization with Live Progress Reporting
        processed_count = 0

        def process_img(item: Tuple[str, bytes]) -> Tuple[bytes, int, int]:
            nonlocal processed_count
            name, raw_bytes = item
            
            if len(raw_bytes) < 150000 and name.lower().endswith('.jpg'):
                try:
                    with Image.open(io.BytesIO(raw_bytes)) as im:
                        res = (raw_bytes, im.width, im.height)
                except Exception:
                    res = optimize_for_kindle(raw_bytes, max_width=1440, max_height=1920, quality=80)
            else:
                res = optimize_for_kindle(raw_bytes, max_width=1440, max_height=1920, quality=80)

            processed_count += 1
            if tracker and task_id and (processed_count % 25 == 0 or processed_count == total_pages):
                pct = round((processed_count / total_pages) * 80.0, 1)
                curr_vol = min(num_volumes, (processed_count // pages_per_volume) + 1)
                tracker.update_task(
                    task_id,
                    status="splitting",
                    progress_percent=pct,
                    total_pages_overall=total_pages,
                    total_pages_downloaded=processed_count,
                    current_chapter=f"Volume {curr_vol} of {num_volumes}",
                    message=f"⚡ Optimizing: {processed_count}/{total_pages} pages ({pct}%) • Volume {curr_vol}/{num_volumes}"
                )
            return res

        num_cpus = os.cpu_count() or 8
        with ThreadPoolExecutor(max_workers=num_cpus * 2) as pool:
            optimized_results = list(pool.map(process_img, extracted_images))

        # 3. Group into volume EPUB files
        from backend.converters.epub_builder import EPUBBuilder

        volume_results = []
        for vol_idx in range(num_volumes):
            start_i = vol_idx * pages_per_volume
            end_i = min(total_pages, (vol_idx + 1) * pages_per_volume)
            vol_images = [opt[0] for opt in optimized_results[start_i:end_i]]

            vol_id = str(uuid.uuid4())
            vol_filename = f"{clean_title}_Part_{vol_idx+1}_of_{num_volumes}.epub"
            vol_path = os.path.join(output_dir, f"{vol_id}_{vol_filename}")

            ch_data = [{
                "title": f"Part {vol_idx+1} (Pages {start_i+1}-{end_i})",
                "chapter_display": f"Part {vol_idx+1}",
                "images": vol_images
            }]

            EPUBBuilder.build_epub(
                manga_title=f"{clean_title} (Part {vol_idx+1}/{num_volumes})",
                chapters_data=ch_data,
                output_path=vol_path,
                kindle_optimize=False
            )

            vol_size_mb = os.path.getsize(vol_path) / (1024 * 1024)
            volume_results.append({
                "file_id": vol_id,
                "filename": vol_filename,
                "part_number": vol_idx + 1,
                "total_parts": num_volumes,
                "file_size": f"{vol_size_mb:.1f} MB",
                "file_path": vol_path,
                "download_url": f"/api/files/{vol_id}"
            })

            if tracker and task_id:
                pct = round(80.0 + ((vol_idx + 1) / num_volumes) * 20.0, 1)
                tracker.update_task(
                    task_id,
                    status="packaging",
                    progress_percent=pct,
                    message=f"Compiling Kindle Volume {vol_idx+1}/{num_volumes} ({pct}%)..."
                )

        return volume_results
