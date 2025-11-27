# Deploy su Railway

Questa guida spiega come deployare l'applicazione VLS Speech-to-Text su Railway.

## Prerequisiti

- Account Railway (https://railway.app)
- Repository GitHub con il codice

## Deploy Rapido

### Metodo 1: Deploy da GitHub (Consigliato)

1. Vai su https://railway.app e accedi
2. Clicca su "New Project"
3. Seleziona "Deploy from GitHub repo"
4. Connetti il tuo account GitHub se necessario
5. Seleziona il repository `vls-speech2text`
6. Railway rileverà automaticamente il `Procfile` e avvierà l'app

### Metodo 2: Deploy via CLI

```bash
# Installa Railway CLI
npm i -g @railway/cli

# Login
railway login

# Inizializza progetto
railway init

# Deploy
railway up
```

## Configurazione

### Variabili d'Ambiente

Railway usa automaticamente la variabile `PORT` - non serve configurarla manualmente.

### Limitazioni su Railway

⚠️ **Importante**: Railway non può compilare FFmpeg con Whisper nativo facilmente.

**Soluzioni:**

1. **Usa Python Whisper** (consigliato per Railway):
   - L'app userà automaticamente `openai-whisper` se FFmpeg Whisper non è disponibile
   - Funziona senza configurazione aggiuntiva

2. **Usa FFmpeg precompilato** (avanzato):
   - Potresti usare un buildpack personalizzato
   - Richiede configurazione avanzata

## Verifica Deploy

Dopo il deploy, Railway ti fornirà un URL tipo:
- `https://vls-speech2text-production.up.railway.app`

Apri l'URL nel browser per verificare che l'app funzioni.

## Aggiornamenti

Ogni push su GitHub triggera automaticamente un nuovo deploy su Railway.

## Troubleshooting

### L'app non si avvia

1. Controlla i log su Railway Dashboard
2. Verifica che `requirements.txt` sia completo
3. Assicurati che la porta sia configurata correttamente (Railway usa `$PORT`)

### FFmpeg non trovato

Su Railway, FFmpeg potrebbe non essere disponibile. L'app userà Python Whisper come fallback automaticamente.

### Modelli Whisper non scaricati

I modelli vengono scaricati automaticamente al primo utilizzo da `openai-whisper`.

## Costi

Railway offre:
- Piano gratuito con $5 di credito mensile
- Pay-as-you-go dopo il credito gratuito

Per un'app con processing video, considera un piano a pagamento per più risorse.

