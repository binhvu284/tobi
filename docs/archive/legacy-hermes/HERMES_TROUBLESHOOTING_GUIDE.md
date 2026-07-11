# 🔧 HERMES - TROUBLESHOOTING & QUICK REFERENCE

---

## ⚡ QUICK COMMANDS REFERENCE

### Essential Commands
```bash
# Check status
hermes doctor
hermes config show
sudo systemctl status hermes

# View logs (real-time)
sudo journalctl -u hermes -f

# Restart service
sudo systemctl restart hermes

# Memory operations
hermes memory
hermes memory search "keyword"
hermes memory optimize

# Skills
hermes skills list
hermes skills reload

# Cron jobs
hermes cron list
hermes cron add --schedule "0 9 * * *" --prompt "..."
hermes cron remove [id]
```

---

## 🐛 TROUBLESHOOTING GUIDE

### Issue 1: Telegram Bot Not Responding

**Symptoms:**
- Send message to bot → No reply
- Logs show errors related to Telegram

**Diagnosis Steps:**
```bash
# Step 1: Check service is running
sudo systemctl status hermes
# Should show: "active (running)"

# Step 2: Check recent logs
sudo journalctl -u hermes -n 50 | grep -i "telegram\|error"

# Step 3: Verify bot token is correct
hermes config show | grep telegram

# Step 4: Test API connection
curl -X GET "https://api.telegram.org/bot[YOUR_TOKEN]/getMe"
# Should return bot info in JSON
```

**Solutions:**

**A. Wrong Bot Token:**
```bash
# Get new token from @BotFather
# Then update:
hermes config set TELEGRAM_BOT_TOKEN "your-new-token-here"
sudo systemctl restart hermes
```

**B. Bot isn't in gateway:**
```bash
# Rebuild gateway setup
hermes gateway setup
# Select: telegram
# Paste new token
# Enter your user ID
```

**C. User not authorized:**
```bash
# Get your actual Telegram user ID
# Send /start to @userinfobot
# Then verify in config:
hermes config show | grep TELEGRAM_USER

# If different, update:
hermes config set TELEGRAM_ALLOWED_USERS "your-actual-id"
sudo systemctl restart hermes
```

**D. Firewall blocking Telegram:**
```bash
# Check outbound connection
telnet api.telegram.org 443
# If hangs → firewall issue

# Or test with curl
curl -I https://api.telegram.org

# Solution: Check VPS firewall rules
# Contact hosting provider to allow outbound HTTPS
```

---

### Issue 2: High API Costs / Token Exhaustion

**Symptoms:**
- Monthly bill higher than expected
- Responses getting slower
- API quota warnings

**Diagnosis:**
```bash
# 1. Check recent token usage
hermes memory search "token" | head -20

# 2. Count recent interactions
sudo journalctl -u hermes --since "2 hours ago" | wc -l

# 3. Check API limit in Anthropic console
# → console.anthropic.com → Usage & billing
```

**Solutions:**

**Quick Fix (Immediate):**
```bash
# Reduce context size
hermes config set max_context_tokens 50000

# Enable compression
hermes config set enable_compression true

# Restart
sudo systemctl restart hermes
```

**Medium Fix (Next Day):**
```bash
# Switch to cheaper model for simple tasks
# Edit ~/.hermes/config/hermes.yaml
# Change: use_haiku_for_simple: true

# Archive old sessions
hermes memory archive --older-than 30

# Compress memory
hermes memory optimize
```

**Long Term Fix:**
```bash
# Implement hybrid model routing (see Cost Optimization guide)
# Setup batch cron jobs instead of interactive
# Use local Ollama for offline tasks

# Monitor spending weekly
hermes cron add --schedule "0 10 * * 1" \
  --prompt "Check API usage. Report monthly spend."
```

---

### Issue 3: Service Won't Start / Crashes

**Symptoms:**
- `sudo systemctl status hermes` shows "failed"
- Service restarts repeatedly
- Logs show errors

**Diagnosis:**
```bash
# Step 1: Check service status with details
sudo systemctl status hermes -l

# Step 2: View full error logs
sudo journalctl -u hermes -n 100

# Step 3: Try starting manually to see errors
/root/.local/bin/hermes --daemon --gateway telegram

# Step 4: Check for missing dependencies
ldd /root/.local/bin/hermes | grep "not found"
```

**Solutions:**

**A. API Key Issue:**
```bash
# Verify API key exists
hermes config show | grep -i anthropic

# If empty, set it:
hermes config set ANTHROPIC_API_KEY "sk-ant-xxxxx"

# Restart
sudo systemctl restart hermes
```

**B. Memory/Disk Full:**
```bash
# Check disk space
df -h

# Check memory usage
free -h

# If disk full, cleanup old sessions:
hermes memory optimize
hermes memory archive --older-than 60
hermes memory purge --older-than 180

# If very low disk, delete old logs:
sudo journalctl --vacuum=100M
```

**C. Port Conflict (if using VPS with other services):**
```bash
# Check what's using ports
sudo netstat -tlnp | grep -E "3000|8000|8080"

# Kill conflicting process if needed
sudo kill -9 [PID]

# Restart Hermes
sudo systemctl restart hermes
```

**D. Configuration Corruption:**
```bash
# Restore from backup
cp ~/.hermes/config/hermes.yaml.backup ~/.hermes/config/hermes.yaml

# Or regenerate from scratch
rm ~/.hermes/config/hermes.yaml
hermes setup  # This may not exist, try:
hermes config set ANTHROPIC_API_KEY "key"
hermes model
```

---

### Issue 4: Telegram Bot Stops Responding (Mid-day)

**Symptoms:**
- Bot was working, suddenly stopped
- Service still shows "running"
- Logs show timeout errors

**Likely Cause:**
- Network hiccup
- Telegram API temporarily down
- Memory leak causing slowdown

**Quick Fix:**
```bash
# Restart just the Telegram gateway
# (without restarting entire service)

# Option A: Full restart
sudo systemctl restart hermes

# Option B: Graceful restart (wait for in-flight requests)
sudo systemctl reload hermes

# Option C: Check and fix
sudo journalctl -u hermes -f  # Watch logs
# ... if you see timeout errors, restart
sudo systemctl restart hermes
```

**Prevent Future Issues:**
```bash
# Add health check cron job
hermes cron add --schedule "*/30 * * * *" \
  --prompt "Are you responsive? Reply 'Yes' if working."

# Or setup automatic restart
# Add to crontab:
*/5 * * * * systemctl is-active hermes || systemctl restart hermes
```

---

### Issue 5: Memory Getting Too Large

**Symptoms:**
- `du -sh ~/.hermes` shows > 500MB
- Searches getting slower
- Agent starting to forget recent things

**Diagnosis:**
```bash
# Check memory size
du -sh ~/.hermes/memory/

# Check session count
hermes memory | grep "Session" | wc -l

# Find largest memory files
find ~/.hermes/memory -type f -exec du -h {} + | sort -rh | head
```

**Solutions:**

**Immediate:**
```bash
# Optimize memory
hermes memory optimize

# Archive old sessions (don't delete, just archive)
hermes memory archive --older-than 30

# Check size after
du -sh ~/.hermes/memory/
```

**Regular Maintenance:**
```bash
# Add monthly cleanup cron job
hermes cron add --schedule "0 2 1 * *" \
  --prompt "
Clean up old memory:
- Archive sessions older than 60 days
- Delete sessions older than 180 days
- Optimize memory database
Report new size.
"
```

---

### Issue 6: Slow Responses

**Symptoms:**
- Requests take 30+ seconds to respond
- Telegram messages get timeout
- CPU/Memory usage high

**Diagnosis:**
```bash
# Check system resources
top -b -n 1 | head -20

# Check disk I/O
iostat -x 1 5

# Check network
ping api.anthropic.com

# Check Hermes logs for slow queries
sudo journalctl -u hermes | grep -i "slow\|timeout"
```

**Solutions:**

**A. System Overloaded:**
```bash
# Check memory usage
free -h

# Kill unnecessary processes
ps aux | grep -i "hermes\|node\|python"
# Kill background apps if needed

# Upgrade VPS if consistently slow
# Switch to better provider (DigitalOcean > Contabo for speed)
```

**B. Model/API Slow:**
```bash
# Switch to faster model temporarily
hermes config set model "claude-3-5-haiku-20241022"  # Faster, cheaper

# Or check Anthropic status
curl -s https://status.anthropic.com  # Check for API issues

# If API issues → use local Ollama while waiting
```

**C. Network Latency:**
```bash
# Test latency to Anthropic
curl -w "@curl-format.txt" -o /dev/null -s https://api.anthropic.com

# If latency > 500ms consistently:
# - Choose VPS closer to Anthropic data center (US-based)
# - Use different provider
```

**D. Context Too Large:**
```bash
# Reduce context window
hermes config set max_context_tokens 50000

# Enable compression
hermes config set enable_compression true

# Restart
sudo systemctl restart hermes
```

---

### Issue 7: Can't SSH into VPS / Lost Access

**Symptoms:**
- SSH connection refused
- Can't reach VPS
- Port 22 issues

**Prevention (Do Now):**
```bash
# Add backup SSH key
# In hosting provider dashboard, add additional SSH key

# Enable root password login (less secure, but backup)
# Log in → Edit sshd_config → PermitRootLogin yes → restart sshd
```

**Recovery:**
```bash
# Use hosting provider's console/recovery mode
# Usually available in control panel

# Once in, get SSH working again:
sudo systemctl restart ssh

# Check status
sudo systemctl status ssh
```

---

## 📊 MONITORING DASHBOARD

### Create Simple Health Check
```bash
# Create monitoring script
cat > ~/hermes_health_check.sh << 'EOF'
#!/bin/bash

echo "=== HERMES HEALTH CHECK ==="
echo ""

echo "✓ Service Status:"
sudo systemctl status hermes --no-pager | head -3

echo ""
echo "✓ Memory Usage:"
ps aux | grep "[h]ermes" | awk '{print $6}' | numfmt --to=iec 2>/dev/null || echo "Check: top"

echo ""
echo "✓ Disk Usage:"
du -sh ~/.hermes/

echo ""
echo "✓ Recent Errors (last 50 lines):"
sudo journalctl -u hermes -n 50 | grep -i "error\|warn" | head -5

echo ""
echo "✓ Telegram Gateway Status:"
sudo journalctl -u hermes -n 20 | grep -i "telegram" | tail -3

echo ""
echo "✓ Last Response Time:"
sudo journalctl -u hermes -n 1 | head -1

EOF

chmod +x ~/hermes_health_check.sh

# Run it
~/hermes_health_check.sh

# Schedule it to run daily at 9 AM
# Add to crontab: (crontab -e)
# 0 9 * * * ~/hermes_health_check.sh >> ~/hermes_health.log
```

---

## 🚨 EMERGENCY COMMANDS

**Immediate Troubleshooting:**
```bash
# 1. Check if service is running
sudo systemctl is-active hermes

# 2. If not, restart
sudo systemctl restart hermes

# 3. Watch logs for 2 minutes
sudo journalctl -u hermes -f --since "2 min ago"

# 4. Check API key
hermes config show | grep API

# 5. Test bot manually
hermes  # opens interactive CLI
# type: "test message"
# press Ctrl+C to exit

# 6. Full restart (nuclear option)
sudo systemctl stop hermes
sleep 5
sudo systemctl start hermes
```

**Recovery from Crash:**
```bash
# 1. Stop everything
sudo systemctl stop hermes

# 2. Check what happened
sudo journalctl -u hermes -n 100 > ~/hermes_error.log
tail ~/hermes_error.log  # view the log

# 3. Fix based on error, then:
sudo systemctl start hermes

# 4. Verify
sudo systemctl status hermes
```

---

## 📞 When to Ask for Help

Collect this info before asking for support:

```bash
# 1. System info
uname -a
cat /etc/os-release

# 2. Hermes version
hermes --version

# 3. Error logs
sudo journalctl -u hermes -n 100 > ~/hermes_error.log

# 4. Config (sanitized)
hermes config show | sed 's/sk-.*/[REDACTED]/g'

# 5. Disk/Memory
df -h
free -h
ps aux | grep hermes

# Send these to support
```

---

## 🎯 PREVENTIVE MAINTENANCE

**Do These Weekly:**
```bash
# Check logs for errors
sudo journalctl -u hermes -n 100 | grep -i error

# Check disk space
df -h /

# Monitor costs
hermes memory search "cost\|api\|usage"
```

**Do These Monthly:**
```bash
# Optimize memory
hermes memory optimize

# Archive old sessions
hermes memory archive --older-than 30

# Update system
sudo apt update && sudo apt upgrade -y

# Verify backups
ls -lh ~/hermes_backup_*
```

**Do These Quarterly:**
```bash
# Full backup
tar -czf ~/hermes_backup_full_$(date +%Y%m%d).tar.gz ~/.hermes/

# Review and trim skills
ls ~/.hermes/skills/
# Delete unused skills to save memory

# Review cron jobs
hermes cron list
# Remove old/unused cron jobs
```

---

## 💡 PRO TIPS

1. **Always backup before major changes:**
   ```bash
   cp -r ~/.hermes ~/hermes_backup_$(date +%Y%m%d)
   ```

2. **Use tmux for long-running operations:**
   ```bash
   tmux new-session -d -s work
   tmux send-keys -t work "hermes" Enter
   tmux attach -t work
   ```

3. **Monitor costs actively:**
   ```bash
   # Check usage weekly
   curl -s -H "Authorization: Bearer $ANTHROPIC_API_KEY" \
     https://api.anthropic.com/billing/usage
   ```

4. **Keep logs for debugging:**
   ```bash
   # Save logs daily
   0 23 * * * sudo journalctl -u hermes --since today > ~/logs/hermes_$(date +\%Y\%m\%d).log
   ```

5. **Test changes in isolated session first:**
   ```bash
   # Don't modify production config directly
   cp ~/.hermes/config/hermes.yaml ~/.hermes/config/hermes.yaml.test
   # Edit test version
   # Then copy to production if works
   ```

---

## 📱 Set Up Alerts

**Via Cron Job (sends to Telegram):**
```bash
hermes cron add --schedule "0 */6 * * *" \
  --prompt "
Check system health:
1. Is Hermes service running?
2. Any errors in recent logs?
3. Disk usage % 
4. API quota status

Alert me if anything abnormal.
"
```

---

**Bạn có vấn đề gì không? Tôi sẵn sàng help troubleshoot! 🚀**
