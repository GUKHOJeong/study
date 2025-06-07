import discord
from discord.ext import commands, tasks
import psycopg2
from datetime import datetime, timedelta, time as dtime
import os
from dotenv import load_dotenv
from zoneinfo import ZoneInfo

# 환경 변수 로딩
load_dotenv()
study_TOKEN = os.getenv("study_token")

# Discord 봇 설정
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# PostgreSQL 연결
conn = psycopg2.connect(
    host=os.getenv("PGHOST"),
    port=os.getenv("PGPORT"),
    user=os.getenv("PGUSER"),
    password=os.getenv("PGPASSWORD"),
    database=os.getenv("PGDATABASE"),
)
cursor = conn.cursor()

# 테이블 생성
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS study_session (
    user_id TEXT PRIMARY KEY,
    started_at TIMESTAMPTZ
);
"""
)

cursor.execute(
    """
CREATE TABLE IF NOT EXISTS study_total (
    user_id TEXT PRIMARY KEY,
    total_minutes INTEGER DEFAULT 0
);
"""
)
conn.commit()

# 공부 명령 허용 채널
STUDY_CHANNEL_ID = 1380862167552757871


# 공부 시작
@bot.command(name="공부시작")
async def start_study(ctx):
    if ctx.channel.id != STUDY_CHANNEL_ID:
        await ctx.send("⚠️ 이 명령어는 지정된 공부 채널에서만 사용할 수 있습니다.")
        return

    user_id = str(ctx.author.id)
    now = datetime.now(ZoneInfo("Asia/Seoul"))

    cursor.execute("SELECT * FROM study_session WHERE user_id = %s", (user_id,))
    row = cursor.fetchone()
    if row:
        started_at = row[1]
        started_at_kst = started_at.astimezone(ZoneInfo("Asia/Seoul"))
        await ctx.send(
            f"{ctx.author.mention} 이미 공부를 시작하셨습니다! 시작 시간: `{started_at_kst.strftime('%H:%M:%S')}`"
        )
        return

    cursor.execute(
        "INSERT INTO study_session (user_id, started_at) VALUES (%s, %s)",
        (user_id, now),
    )
    conn.commit()
    await ctx.send(f"{ctx.author.mention} 공부 시작 기록 완료! 📝")


# 공부 종료
@bot.command(name="공부종료")
async def end_study(ctx):
    if ctx.channel.id != STUDY_CHANNEL_ID:
        await ctx.send("⚠️ 이 명령어는 지정된 공부 채널에서만 사용할 수 있습니다.")
        return

    user_id = str(ctx.author.id)
    now = datetime.now(ZoneInfo("Asia/Seoul"))

    cursor.execute(
        "SELECT started_at FROM study_session WHERE user_id = %s", (user_id,)
    )
    row = cursor.fetchone()
    if not row:
        await ctx.send(f"{ctx.author.mention} 공부를 시작하지 않으셨습니다!")
        return

    started_at = row[0].astimezone(ZoneInfo("Asia/Seoul"))
    minutes = int((now - started_at).total_seconds() // 60)

    cursor.execute("DELETE FROM study_session WHERE user_id = %s", (user_id,))
    cursor.execute(
        """
        INSERT INTO study_total (user_id, total_minutes)
        VALUES (%s, %s)
        ON CONFLICT (user_id)
        DO UPDATE SET total_minutes = study_total.total_minutes + EXCLUDED.total_minutes;
    """,
        (user_id, minutes),
    )
    conn.commit()

    await ctx.send(f"{ctx.author.mention} 공부 종료! ⏰ 총 {minutes}분 공부했습니다.")


# 랭킹 확인
@bot.command(name="랭킹")
async def show_ranking(ctx):
    if ctx.channel.id != STUDY_CHANNEL_ID:
        await ctx.send("⚠️ 이 명령어는 지정된 공부 채널에서만 사용할 수 있습니다.")
        return

    cursor.execute(
        "SELECT user_id, total_minutes FROM study_total ORDER BY total_minutes DESC LIMIT 5"
    )
    rows = cursor.fetchall()

    if not rows:
        await ctx.send("아직 아무도 공부를 시작하지 않았어요 😴")
        return

    message = "**📊 이번 주 공부 랭킹 TOP 5!**\n"
    for i, (user_id, minutes) in enumerate(rows, start=1):
        mention = f"<@{user_id}>"
        message += f"{i}. {mention} — {minutes}분\n"

    await ctx.send(message)


# 주간 초기화 (월요일 00:00 기준)
@tasks.loop(time=dtime(hour=0, minute=0))
async def reset_weekly():
    today = datetime.now(ZoneInfo("Asia/Seoul"))
    if today.weekday() == 0:  # 월요일
        cursor.execute("UPDATE study_total SET total_minutes = 0")
        conn.commit()
        print("✅ 주간 공부 시간 초기화 완료")


@bot.event
async def on_ready():
    print(f"📚 공부 봇 로그인됨: {bot.user}")
    reset_weekly.start()


# 실행
bot.run(study_TOKEN)
