import streamlit as st
import json, os, re, numpy as np, imageio, subprocess, tempfile
from PIL import Image, ImageDraw, ImageFont
from openai import OpenAI
from dotenv import load_dotenv
import shutil

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

FPS = 30
WIDTH, HEIGHT = 1080, 1920 
FONT_PATH = "/System/Library/Fonts/Supplemental/Arial.ttf"

st.set_page_config(
    page_title="Video Ad Generator",
    page_icon="🎥",
    layout="wide",
    initial_sidebar_state="expanded"
)


st.sidebar.header("🎯 Ad Settings")
uploaded_files = st.sidebar.file_uploader(
    "📸 **Upload product images (1-10)**", type=["png","jpg","jpeg"], accept_multiple_files=True
)
music_file = st.sidebar.file_uploader(
    "🎵 **Optional: Upload background music (mp3)**", type=["mp3"], accept_multiple_files=False
)
ad_description = st.sidebar.text_area(
    "✏️ **Describe your ad**",
    placeholder="e.g., 5s vertical video, clean & modern, hero shot of bag, reveal mini bag, final CTA..."
)
aspect_choice = st.sidebar.radio("📐 **Aspect Ratio**", ["Instagram 9:16", "YouTube 16:9"])
if aspect_choice == "Instagram 9:16":
    WIDTH, HEIGHT = 1080, 1920
else:
    WIDTH, HEIGHT = 1920, 1080

generate_btn = st.sidebar.button("🚀 Generate Video Ad", type="primary")
st.sidebar.markdown("---")
st.sidebar.markdown(
    "💡 **Tip:** Upload multiple angles of your product and describe motions, durations, and text overlays for best results."
)

st.title("🎥 Video Ad Generator")
st.markdown(
    "<p style='font-size:18px; color:#333;'>Generate professional Instagram/Youtube-ready video ads automatically from your product images, optional music, and description.</p>",
    unsafe_allow_html=True
)

def apply_camera_motion(img, frame, total_frames, motion):
    w, h = img.size
    if motion == "zoom_in":
        scale = 1 + 0.15 * (frame / total_frames)
    elif motion == "zoom_out":
        scale = 1.15 - 0.15 * (frame / total_frames)
    elif motion == "pan_left":
        scale = 1.1
    else:
        scale = 1.0

    new_w, new_h = int(w * scale), int(h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    x = max(0, (new_w - WIDTH)//2)
    y = max(0, (new_h - HEIGHT)//2)
    if motion == "pan_left":
        x = int((new_w - WIDTH) * (frame / total_frames))

    return img.crop((x, y, x + WIDTH, y + HEIGHT))

def fit_image(img):
    img_ratio = img.width / img.height
    frame_ratio = WIDTH / HEIGHT
    if img_ratio > frame_ratio:
        new_w = WIDTH
        new_h = int(WIDTH / img_ratio)
    else:
        new_h = HEIGHT
        new_w = int(HEIGHT * img_ratio)
    img_resized = img.resize((new_w, new_h), Image.LANCZOS)
    frame = Image.new("RGB", (WIDTH, HEIGHT), (0,0,0))
    frame.paste(img_resized, ((WIDTH-new_w)//2, (HEIGHT-new_h)//2))
    return frame

def draw_animated_text(img, text, frame, total_frames):
    draw = ImageDraw.Draw(img, "RGBA")
    try:
        font = ImageFont.truetype(FONT_PATH, 70)
    except:
        font = ImageFont.load_default()
    progress = frame / total_frames
    alpha = int(255 * min(progress*2, 1))
    x = WIDTH // 2
    y = int(HEIGHT * 0.75 - 50*(1 - progress))
    bbox = draw.textbbox((0,0), text, font=font)
    text_w = bbox[2] - bbox[0]
    draw.text((x - text_w//2, y), text, fill=(255,255,255,alpha), font=font)

def parse_ai_json(raw_text):
    try:
        match = re.search(r"\{.*\}", raw_text, flags=re.DOTALL)
        if match:
            return json.loads(match.group())
        return {}
    except Exception as e:
        print("JSON parse error:", e)
        return {}

def generate_scene_json(description):
    user_prompt = f"""
Create a scene plan for a vertical video ad based on this description:
{description}

Rules:
- Return JSON with key "scenes": [{{"image_index": 0, "duration": 1.5, "motion":"zoom_in", "text":"Scene text"}}]
- Use motions: zoom_in, zoom_out, pan_left, none
- Provide duration per scene in seconds
- Respect order of scenes
- Maximum 10 scenes
- Return ONLY valid JSON, no explanations
"""
    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role":"system","content":"You are a professional ad director. Return ONLY valid JSON."},
            {"role":"user","content":user_prompt}
        ],
        temperature=0.4
    )
    return parse_ai_json(res.choices[0].message.content)

def render_video(images, scene_plan, output="final_ad.mp4"):
    if len(images) == 0 or len(scene_plan.get("scenes", [])) == 0:
        st.error("No images or scenes to render.")
        return
    writer = imageio.get_writer(output, fps=FPS, codec="libx264")
    for scene in scene_plan["scenes"]:
        idx = min(scene.get("image_index",0), len(images)-1)
        img = images[idx].copy()
        img = fit_image(img)
        frames = max(1, int(scene.get("duration",1.5) * FPS))
        motion = scene.get("motion","none")
        text = scene.get("text","")
        for f in range(frames):
            frame_img = apply_camera_motion(img, f, frames, motion)
            draw_animated_text(frame_img, text, f, frames)
            writer.append_data(np.array(frame_img))
    writer.close()

def add_music_ffmpeg(video_path, music_path, output_path="final_ad_with_music.mp4"):
    if not shutil.which("ffmpeg"):
        st.warning("⚠️ FFmpeg not found. Video generated without music.")
        return video_path 
    subprocess.run([
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", music_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        output_path
    ])
    return output_path

if generate_btn:
    if not uploaded_files:
        st.sidebar.error("Please upload at least one image.")
    elif not ad_description.strip():
        st.sidebar.error("Please write an ad description.")
    else:
        images = [Image.open(f).convert("RGB") for f in uploaded_files]
        with st.spinner("AI generating scene plan..."):
            scene_plan = generate_scene_json(ad_description)

        if scene_plan.get("scenes"):
            with st.spinner("Rendering video..."):
                temp_video = "final_ad.mp4"
                render_video(images, scene_plan, output=temp_video)

                final_video_path = temp_video
                if music_file:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                        tmp.write(music_file.read())
                        music_path = tmp.name
                    final_video_path = add_music_ffmpeg(temp_video, music_path)

            st.success("✅ Video Generated!")
            st.video(final_video_path)
            with open(final_video_path,"rb") as f:
                st.download_button("⬇️ Download Video", f, file_name="ai_video_ad.mp4", mime="video/mp4")
        else:
            st.error("No scenes generated. Try a simpler description.")
