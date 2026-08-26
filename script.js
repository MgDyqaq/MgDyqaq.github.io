document.getElementById('theme-toggle').addEventListener('click', () => {
    const body = document.body;
    const currentTheme = body.getAttribute('data-theme');
    body.setAttribute('data-theme', currentTheme === 'dark' ? 'light' : 'dark');
});

document.getElementById('submit-btn').addEventListener('click', async () => {
    const code = document.getElementById('code-input').value;
    if (!code.trim()) {
        alert("奏折不能为空！");
        return;
    }

    const runId = Date.now().toString();
    const submitBtn = document.getElementById('submit-btn');
    submitBtn.disabled = true;
    submitBtn.textContent = "⏳ 御览中...";

    // 1. Trigger GitHub Action via Workflow Dispatch
    // Note: You need a Personal Access Token (PAT) with repo scope
    // For security, in production, use a backend proxy. Here we assume client-side for demo.
    // WARNING: Exposing PAT in client-side JS is insecure. Use a backend or GitHub App.
    
    try {
        await fetch(`https://api.github.com/repos/MgDyqaq/MgDyqaq.github.io/actions/workflows/judge.yml/dispatches`, {
            method: 'POST',
            headers: {
                'Authorization': 'token None', // Replace with your PAT
                'Accept': 'application/vnd.github.v3+json'
            },
            body: JSON.stringify({
                ref: 'main',
                inputs: {
                    code: btoa(code), // Base64 encode to avoid JSON issues
                    run_id: runId
                }
            })
        });

        pollResult(runId);
    } catch (error) {
        console.error(error);
        alert("呈递失败，请检查网络或权限。");
        submitBtn.disabled = false;
        submitBtn.textContent = "🚀 呈递御览";
    }
});

async function pollResult(runId) {
    const resultArea = document.getElementById('result-area');
    const scoreDisplay = document.getElementById('score-display');
    const detailsGrid = document.getElementById('details-grid');
    const successImg = document.getElementById('success-img');
    
    resultArea.classList.remove('hidden');
    scoreDisplay.textContent = "批阅中...";
    detailsGrid.innerHTML = "";
    successImg.classList.add('hidden');

    const maxAttempts = 60; // 5 minutes max
    let attempts = 0;

    const interval = setInterval(async () => {
        attempts++;
        try {
            // Fetch result from results-branch raw URL
            const response = await fetch(`https://raw.githubusercontent.com/MgDyqaq/MgDyqaq.github.io/results-branch/results/${runId}.json`);
            
            if (response.ok) {
                const data = await response.json();
                displayResult(data);
                clearInterval(interval);
                document.getElementById('submit-btn').disabled = false;
                document.getElementById('submit-btn').textContent = "🚀 呈递御览";
            } else if (attempts >= maxAttempts) {
                scoreDisplay.textContent = "批阅超时";
                clearInterval(interval);
            }
        } catch (e) {
            // Ignore network errors during polling
        }
    }, 5000); // Poll every 5 seconds
}

function displayResult(data) {
    const scoreDisplay = document.getElementById('score-display');
    const detailsGrid = document.getElementById('details-grid');
    const successImg = document.getElementById('success-img');

    scoreDisplay.textContent = `得分：${data.score} / 100`;
    
    detailsGrid.innerHTML = '';
    data.details.forEach(point => {
        const div = document.createElement('div');
        div.className = `test-point ${point.status}`;
        div.textContent = `#${point.id} ${point.status}`;
        detailsGrid.appendChild(div);
    });

    if (data.score === 100) {
        successImg.classList.remove('hidden');
        // Reset animation
        successImg.style.animation = 'none';
        successImg.offsetHeight; /* trigger reflow */
        successImg.style.animation = 'fadeOut 5s forwards';
    }
}
