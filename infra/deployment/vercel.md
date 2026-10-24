# Vercel Frontend Deployment

1. Import the repository in Vercel.
2. Set Root Directory to `frontend`.
3. Set `NEXT_PUBLIC_API_BASE_URL` to the deployed backend API base URL.
4. Never put Gemini or database secrets in `NEXT_PUBLIC_*`.
5. Configure backend CORS to the exact deployed frontend origin.
6. Test auth, API errors and browser network requests.
7. Review plan limits; free tier is not an uptime guarantee.
