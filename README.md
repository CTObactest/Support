# Telegram Support Bot - Deployment Guide

## Overview
This guide covers deploying a Telegram support bot with MongoDB database and dynamic group connection features on Koyeb.

## Prerequisites

### 1. Telegram Bot Setup
1. Message [@BotFather](https://t.me/botfather) on Telegram
2. Create a new bot: `/newbot`
3. Choose a name and username for your bot
4. Save the bot token (format: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)
5. Configure bot settings:
   ```
   /setcommands
   start - Show main menu
   help - Get help information
   connect - Connect group as support group (groups only)
   disconnect - Disconnect support group (groups only)
   ```

### 2. MongoDB Setup

**Option A: MongoDB Atlas (Recommended)**
1. Go to [MongoDB Atlas](https://www.mongodb.com/atlas)
2. Create a free cluster
3. Create a database user
4. Whitelist your IP addresses (or use 0.0.0.0/0 for all IPs)
5. Get your connection string: `mongodb+srv://username:password@cluster.mongodb.net/support_bot`

**Option B: Self-hosted MongoDB**
1. Set up MongoDB server
2. Create database and user
3. Connection string: `mongodb://username:password@host:port/support_bot`

## Deployment on Koyeb

### Method 1: GitHub Integration (Recommended)

1. **Prepare Your Repository**
   ```bash
   git clone <your-repo>
   cd telegram-support-bot
   # Add all the bot files (bot.py, requirements.txt, Dockerfile)
   git add .
   git commit -m "Initial bot setup"
   git push origin main
   ```

2. **Deploy on Koyeb**
   - Go to [Koyeb Dashboard](https://app.koyeb.com)
   - Click "Create App"
   - Choose "GitHub" as source
   - Select your repository
   - Configure build settings:
     - **Build command**: `pip install -r requirements.txt`
     - **Run command**: `python bot.py`
     - **Port**: `8000`

3. **Environment Variables**
   Set these in Koyeb app settings:
   ```bash
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/support_bot
   PORT=8000
   WEBHOOK_URL=https://your-app-name.koyeb.app
   ```

### Method 2: Docker Deployment

1. **Build and Push Docker Image**
   ```bash
   # Build image
   docker build -t your-username/telegram-support-bot .
   
   # Push to Docker Hub
   docker push your-username/telegram-support-bot
   ```

2. **Deploy on Koyeb**
   - Choose "Docker" as source
   - Image: `your-username/telegram-support-bot:latest`
   - Port: `8000`
   - Set environment variables as above

## Configuration

### 1. Set Telegram Webhook
After deployment, configure the webhook:

```bash
curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook" \
     -H "Content-Type: application/json" \
     -d '{
       "url": "https://your-koyeb-app.koyeb.app/webhook",
       "allowed_updates": ["message", "callback_query"]
     }'
```

### 2. Verify Webhook
Check webhook status:
```bash
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getWebhookInfo"
```

## Setting Up Support Groups

### 1. Create Support Group
1. Create a new Telegram group
2. Add your support team members
3. Make sure at least one admin is present

### 2. Connect Group to Bot
1. Add your bot to the support group
2. Make the bot an admin (optional, but recommended)
3. An admin should use `/connect` command
4. Click "Connect as Support Group" button
5. Confirmation message will appear

### 3. Managing Connected Groups
- **View connected groups**: Check bot logs or MongoDB `groups` collection
- **Disconnect group**: Use `/disconnect` command in the group
- **Multiple groups**: You can connect multiple support groups

## Knowledge Base Management

### 1. Initial Setup
The bot creates default FAQ entries automatically. You can modify them by:

**Option A: Direct Database Update**
```javascript
// Connect to MongoDB and update knowledge_base collection
db.knowledge_base.updateOne(
  {"question": "how to login"},
  {"$set": {"answer": "Your updated login instructions..."}}
)

// Add new FAQ entry
db.knowledge_base.insertOne({
  "question": "new question",
  "answer": "Detailed answer...",
  "category": "general",
  "keywords": ["keyword1", "keyword2"],
  "created_at": new Date(),
  "status": "published"
})
```

**Option B: Admin Interface (Future Enhancement)**
You can extend the bot to include admin commands for KB management.

### 2. FAQ Categories
Default categories:
- `general` - General questions
- `technical` - Technical issues
- `billing` - Payment and subscription
- `account` - User account related
- `feature_request` - Feature suggestions

## Monitoring and Maintenance

### 1. Logs
Monitor your bot through Koyeb logs:
- Go to your app in Koyeb dashboard
- Click on "Logs" tab
- Monitor for errors and performance

### 2. Database Monitoring
**Key metrics to monitor:**
```javascript
// Ticket statistics
db.tickets.aggregate([
  {"$group": {
    "_id": "$status",
    "count": {"$sum": 1}
  }}
])

// Support group activity
db.groups.find({"status": "active"})

// Popular FAQ searches
db.knowledge_base.find().sort({"views": -1}).limit(10)
```

### 3. Performance Optimization
- **Database indexes**: Already configured automatically
- **Connection pooling**: Handled by Motor driver
- **Memory usage**: Monitor through Koyeb metrics

## Troubleshooting

### Common Issues

**1. Webhook Not Working**
```bash
# Check webhook status
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"

# Reset webhook
curl -X POST "https://api.telegram.org/bot<TOKEN>/deleteWebhook"
# Then set it again
```

**2. Database Connection Issues**
- Check MongoDB URI format
- Verify network access (IP whitelist)
- Check MongoDB Atlas cluster status

**3. Bot Not Responding in Groups**
- Ensure bot has necessary permissions
- Check if bot username is mentioned in group messages
- Verify group connection status in database

**4. Tickets Not Forwarding**
- Check connected groups: `db.groups.find({"status": "active"})`
- Verify bot is still member of support groups
- Check bot permissions in support groups

### Debug Mode
For local testing, you can enable debug mode:
```python
# In bot.py, change logging level
logging.basicConfig(level=logging.DEBUG)

# Use polling instead of webhook for local testing
# Comment out webhook configuration and use:
app.run_polling()
```

## Security Considerations

1. **Environment Variables**: Never commit bot tokens to repository
2. **MongoDB Security**: Use strong passwords and IP restrictions
3. **Group Permissions**: Only allow trusted admins to connect groups
4. **Data Privacy**: Implement data retention policies
5. **Rate Limiting**: Monitor for abuse and implement rate limits if needed

## Scaling and Advanced Features

### Future Enhancements
1. **Multi-language support**: Add language detection and responses
2. **AI Integration**: Connect to OpenAI or similar for smart responses
3. **Analytics Dashboard**: Web interface for ticket and KB analytics
4. **File Attachments**: Support for images and documents in tickets
5. **SLA Management**: Automatic escalation and response time tracking
6. **Integration APIs**: Connect with external ticketing systems

### Performance Scaling
- **Database**: Use MongoDB sharding for large datasets
- **Application**: Deploy multiple instances with load balancing
- **Caching**: Implement Redis for frequently accessed data
- **CDN**: Use CDN for static assets if adding web interface

## Support and Maintenance

### Regular Tasks
1. **Weekly**: Review ticket metrics and support group activity
2. **Monthly**: Update knowledge base with new FAQs
3. **Quarterly**: Review and optimize database performance
4. **As needed**: Update bot features and security patches

### Backup Strategy
```javascript
// MongoDB backup script
mongodump --uri="your_mongodb_uri" --out=/backup/$(date +%Y%m%d)

// Restore if needed
mongorestore --uri="your_mongodb_uri" /backup/20250526
```

This deployment guide provides a complete setup for a production-ready Telegram support bot with MongoDB integration and dynamic group management features.
