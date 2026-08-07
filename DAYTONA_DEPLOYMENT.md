# Daytona Deployment Guide

## Overview

This guide will help you deploy Music Suggest Bot to Daytona for 24/7 operation.

## Prerequisites

- Daytona account: https://app.daytona.io/dashboard/sandboxes
- GitHub repository: https://github.com/susispolo/ggooozz
- Telegram Bot Token from @BotFather

## Step 1: Prepare Repository

### Clean up sensitive files (already done)

The following files have been removed from git tracking:
- `feature_cache.db` (database)
- `user_prefs.db` (database)
- `bot.log` (logs)
- `cached_songs.json` (9.7MB cache)

### Update .gitignore (already done)

Added proper exclusions for:
- Database files (`*.db`)
- Log files (`*.log`)
- Cache files (`cached_songs.json`)
- IDE files
- OS files

## Step 2: Push to GitHub

```bash
cd D:\music-suggest-bot

# Stage all changes
git add .
git add -A

# Commit deployment preparation
git commit -m "Prepare for Daytona deployment: clean git tracking, add Docker configs"

# Push to GitHub
git push origin main
```

## Step 3: Create Daytona Sandbox

1. Log in to https://app.daytona.io/dashboard/sandboxes
2. Click **"New Sandbox"**
3. Select **"Docker"** as the runtime
4. Connect your GitHub repository:
   - Repository: `https://github.com/susispolo/ggooozz`
   - Branch: `main`
5. Configure the sandbox:
   - **Name**: `music-suggest-bot`
   - **CPU**: 2 vCPU
   - **Memory**: 2 GB
   - **Disk**: 10 GB
6. Click **"Create"**

## Step 4: Set Environment Variables

In the Daytona dashboard, go to your sandbox → **Settings** → **Environment Variables**

Add these variables:

```bash
# Required
TELEGRAM_BOT_TOKEN=your_token_here

# Optional (for better recommendations)
LASTFM_API_KEY=your_key_here
AUDD_API_TOKEN=your_token_here

# Configuration
ENABLE_PREFETCH=true
PREFETCH_MODE=artist
PORT=8080
```

## Step 5: Deploy and Start

1. Daytona will automatically build the Docker image
2. The bot will start automatically
3. Check logs in the dashboard to verify startup

### Expected Startup Output

```
==================================================
  MUSIC SUGGEST BOT v3
  Full Featured Music Discovery Platform
==================================================

  Commands:
  /start, /help, /random, /compare
  /mood, /activity, /playlist, /trivia
  /profile, /recommend, /lyrics, /dna
  /share, /top, /chart, /history
==================================================

Bot initialized: Last.fm=OK
[SCHEDULER] Artist-based prefetch scheduler started
[SCHEDULER] Will fetch: 200 pop, 100 rap, 100 persian, 100 rock artists
Application started
```

## Step 6: Verify Bot is Working

1. Open Telegram
2. Search for your bot
3. Send `/start`
4. Test a search: `Bohemian Rhapsody`
5. Send `/prefetch` to see cache status

## Step 7: Monitor Performance

### Check Logs

In Daytona dashboard → **Logs** tab

### Check Cache Status

Send `/prefetch` to your bot on Telegram

### Expected Cache Growth

- **First hour**: ~100-500 songs cached
- **After 24 hours**: ~5,000-10,000 songs
- **After 1 week**: ~50,000+ songs

## Danger Zones & Solutions

### ⚠️ Danger Zone 1: Database Growth

**Problem**: Database files can grow to several GB

**Solution**: 
- Automatic cleanup runs daily at 3 AM
- Removes entries older than 30 days
- Manual cleanup: Send `/prefetch` and check stats

### ⚠️ Danger Zone 2: Memory Usage

**Problem**: Librosa analysis uses significant RAM

**Solution**:
- Semaphore limits concurrent analyses to 4
- Monitor memory in Daytona dashboard
- Scale up if needed (4GB RAM)

### ⚠️ Danger Zone 3: API Rate Limits

**Problem**: MusicBrainz (1 req/sec), Last.fm (5 req/sec)

**Solution**:
- Built-in rate limiting in clients
- Prefetch respects limits
- Automatic retry with backoff

### ⚠️ Danger Zone 4: Preview URL Expiration

**Problem**: Deezer preview URLs expire after ~5 minutes

**Solution**:
- Fetch fresh URLs when needed
- Cache audio features, not URLs
- Re-analyze if features missing

### ⚠️ Danger Zone 5: Process Crashes

**Problem**: Bot may crash due to errors

**Solution**:
- Docker restart policy: `unless-stopped`
- Health checks every 30 seconds
- Automatic restart on failure

## Performance Optimization

### Current Performance

- **Search response**: <1 second (cached songs)
- **First analysis**: 10-30 seconds
- **Prefetch speed**: ~10-15 songs/minute
- **Memory usage**: ~500MB-1GB

### Scaling Recommendations

**For 100 concurrent users:**
- CPU: 2 vCPU (current)
- Memory: 2 GB (current)
- Storage: 10 GB

**For 1000 concurrent users:**
- CPU: 4 vCPU
- Memory: 4 GB
- Storage: 50 GB
- Consider: Redis cache, PostgreSQL

## Troubleshooting

### Bot Won't Start

1. Check environment variables are set
2. Verify TELEGRAM_BOT_TOKEN is valid
3. Check logs for errors

### Bot is Slow

1. Check if prefetch is running: `/prefetch`
2. Monitor API rate limits in logs
3. Check memory usage

### Songs Not Being Cached

1. Check MusicBrainz errors in logs
2. Verify preview URLs are accessible
3. Check database connection

### High Memory Usage

1. Restart bot: Docker restart
2. Reduce prefetch target in code
3. Scale up memory allocation

## Backup Strategy

### Database Files

The bot uses SQLite databases:
- `feature_cache.db` - Audio features cache
- `user_prefs.db` - User data

### Backup Commands

```bash
# Backup databases
cp data/feature_cache.db data/feature_cache.db.backup
cp data/user_prefs.db data/user_prefs.db.backup

# Or use Daytona snapshot feature
```

### Restore

```bash
# Stop bot
docker-compose down

# Restore databases
cp data/feature_cache.db.backup data/feature_cache.db
cp data/user_prefs.db.backup data/user_prefs.db

# Start bot
docker-compose up -d
```

## Cost Optimization

### Daytona Pricing

- **Sandbox**: ~$0.03/hour
- **24/7 operation**: ~$21.60/month
- **With 2 vCPU + 2GB RAM**: ~$30-40/month

### Cost Reduction Tips

1. **Use reserved instances** if available
2. **Monitor usage** and scale down during low-traffic periods
3. **Optimize code** to reduce CPU/memory usage
4. **Use caching** to minimize API calls

## Security Considerations

### ✅ Already Implemented

- Environment variables for secrets
- .env file in .gitignore
- No hardcoded API keys
- Database files not in git

### ✅ Additional Recommendations

1. **Enable HTTPS** (Daytona provides this)
2. **Set up alerts** for failed logins
3. **Monitor API usage** for anomalies
4. **Regular updates** to dependencies

## Next Steps

1. ✅ Push cleaned code to GitHub
2. ✅ Create Daytona sandbox
3. ✅ Set environment variables
4. ✅ Verify bot is working
5. ✅ Monitor for 24 hours
6. ✅ Optimize based on usage

## Support

- **Daytona Docs**: https://docs.daytona.io
- **GitHub Issues**: https://github.com/susispolo/ggooozz/issues
- **Bot Logs**: Check Daytona dashboard

---

**Last Updated**: 2026-08-07
**Version**: 1.0.0
