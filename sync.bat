@echo off
echo Syncing to both backends...
git push origin main
git push whatsapp whatsapp-integration-updates
echo Done! VPS (origin/main) and Vercel (whatsapp/whatsapp-integration-updates) are in sync.
pause
