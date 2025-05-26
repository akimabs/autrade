from PIL import Image, ImageDraw, ImageFont

def create_trading_report(symbol, pnl, trade_time, output_path, bot_name="autrade", background_path="./assets/bg.png"):
    # Load chart background dan resize
    bg = Image.open(background_path).convert("RGBA").resize((1150, 768))
    draw = ImageDraw.Draw(bg)

    # Load font
    font_large = ImageFont.truetype("./assets/DejaVuSans-Bold.ttf", 80)
    font_medium = ImageFont.truetype("./assets/DejaVuSans-Bold.ttf", 40)
    font_small = ImageFont.truetype("./assets/DejaVuSans.ttf", 30)

    # Hitung warna PnL
    pnl_color = (0, 255, 0) if pnl >= 0 else (255, 0, 0)
    pnl_text = f"{'+' if pnl >= 0 else ''}{pnl:.2f}%"

    # Posisi teks (kiri)
    margin_left = 80
    draw.text((margin_left, 180), symbol, font=font_medium, fill="white")
    draw.text((margin_left, 250), pnl_text, font=font_large, fill=pnl_color)
    draw.text((margin_left, 370), trade_time, font=font_small, fill="white")
    draw.text((margin_left, 670), bot_name, font=font_small, fill="white")

    # Simpan ke file
    bg.save(output_path)
    
def create_summary_report(
    total, win, loss, winrate, net_pnl, net_pct,
    output_path, background_path="./assets/bg.png", bot_name="autrade", mode="Summary"
):
    from PIL import Image, ImageDraw, ImageFont

    # Load background dan resize
    bg = Image.open(background_path).convert("RGBA").resize((1150, 768))
    draw = ImageDraw.Draw(bg)

    # Load fonts
    font_large = ImageFont.truetype("./assets/DejaVuSans-Bold.ttf", 60)
    font_medium = ImageFont.truetype("./assets/DejaVuSans-Bold.ttf", 30)
    font_small = ImageFont.truetype("./assets/DejaVuSans.ttf", 24)

    # Format teks
    pnl_color = (0, 255, 0) if net_pnl >= 0 else (255, 0, 0)
    pnl_pct_text = f"{'+' if net_pct >= 0 else ''}{net_pct:.2f}%"
    pnl_usdt_text = f"{'+' if net_pnl >= 0 else ''}{net_pnl:.2f} USDT"
    winrate_text = f"{winrate:.2f}%"
    trade_summary = f"Total: {total}x | Win: {win} | Loss: {loss}"

    # Posisi teks (kiri)
    margin_left = 80
    draw.text((margin_left, 150), mode, font=font_medium, fill="white")

    draw.text((margin_left, 230), "Net PnL (USDT)", font=font_small, fill="white")
    draw.text((margin_left, 260), pnl_usdt_text, font=font_large, fill=pnl_color)

    draw.text((margin_left, 340), "Net PnL (%)", font=font_small, fill="white")
    draw.text((margin_left, 370), pnl_pct_text, font=font_large, fill=pnl_color)

    draw.text((margin_left, 460), f"Winrate: {winrate_text}", font=font_medium, fill="white")
    draw.text((margin_left, 510), trade_summary, font=font_small, fill="white")

    draw.text((margin_left, 700), bot_name, font=font_small, fill="white")

    # Simpan ke file
    bg.save(output_path)