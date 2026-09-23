const https = require('https');
const http = require('http');

function fetchUrl(url, maxRedirects = 5) {
    return new Promise((resolve, reject) => {
        const client = url.startsWith('https') ? https : http;
        const req = client.get(url, {
            headers: {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8',
            },
            timeout: 15000,
        }, (res) => {
            if ((res.statusCode === 301 || res.statusCode === 302) && res.headers.location && maxRedirects > 0) {
                let redirectUrl = res.headers.location;
                if (redirectUrl.startsWith('/')) {
                    const parsed = new URL(url);
                    redirectUrl = parsed.origin + redirectUrl;
                }
                return fetchUrl(redirectUrl, maxRedirects - 1).then(resolve).catch(reject);
            }
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => resolve({ status: res.statusCode, body: data, finalUrl: url }));
        });
        req.on('error', reject);
        req.on('timeout', () => { req.destroy(); reject(new Error('timeout')); });
    });
}

module.exports = async (req, res) => {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.method === 'OPTIONS') {
        return res.status(200).end();
    }

    if (req.method !== 'POST') {
        return res.status(405).json({ error: 'Method not allowed' });
    }

    const { url } = req.body || {};
    if (!url || !url.includes('shein')) {
        return res.status(400).json({ error: 'Link Shein invalido' });
    }

    try {
        // Step 1: resolve onelink → real product URL
        let page = await fetchUrl(url);
        let html = page.body;

        // extract real URL from onelink page
        const urlMatch = html.match(/<input id="url" value="([^"]+)"/);
        if (urlMatch) {
            let realUrl = urlMatch[1].replace(/&amp;/g, '&').split('?')[0];
            try {
                page = await fetchUrl(realUrl);
                html = page.body;
            } catch (e) {
                // continue with original html
            }
        }

        // Step 2: extract title
        let title = 'Produto Shein';
        const titleMatch = html.match(/property="og:title"\s+content="([^"]+)"/i)
            || html.match(/<title[^>]*>([^<]+)<\/title>/i);
        if (titleMatch) {
            title = titleMatch[1].trim();
        }

        // Step 3: extract images
        const images = new Set();

        // og:image
        const ogImg = html.match(/property="og:image"\s+content="([^"]+)"/i);
        if (ogImg) images.add(ogImg[1]);

        // img.ltwebstatic.com images (product photos)
        const imgRegex = /https?:\/\/img\.ltwebstatic\.com\/[^"'\s<>\\]+?\.(?:jpg|jpeg|png|webp)/gi;
        let m;
        while ((m = imgRegex.exec(html)) !== null) {
            const imgUrl = m[0].replace(/\\/g, '');
            if (imgUrl.includes('j/pi') || imgUrl.includes('images') || imgUrl.includes('good')) {
                images.add(imgUrl);
            }
        }

        // also try //img pattern
        const imgRegex2 = /(?:https?:)?\/\/img\.ltwebstatic\.com\/[^"'\s<>\\]+?\.(?:jpg|jpeg|png|webp)/gi;
        while ((m = imgRegex2.exec(html)) !== null) {
            let imgUrl = m[0];
            if (!imgUrl.startsWith('http')) imgUrl = 'https:' + imgUrl;
            imgUrl = imgUrl.replace(/\\/g, '');
            if (imgUrl.includes('j/pi') || imgUrl.includes('images') || imgUrl.includes('good')) {
                images.add(imgUrl);
            }
        }

        // Step 4: extract videos
        const videos = new Set();
        const vidRegex = /https?:\/\/[^"'\s<>\\]+?\.mp4[^"'\s<>\\]*/gi;
        while ((m = vidRegex.exec(html)) !== null) {
            videos.add(m[0].replace(/["';]$/g, ''));
        }

        // Step 5: try fetch product detail page for more images
        if (images.size < 3) {
            const pidMatch = html.match(/p-(\d+)/);
            if (pidMatch) {
                try {
                    const detailUrl = `https://br.shein.com/pdsearch/${pidMatch[1]}/`;
                    const detailPage = await fetchUrl(detailUrl);
                    const detailHtml = detailPage.body;
                    const moreImgs = detailHtml.match(/https?:\/\/img\.ltwebstatic\.com\/[^"'\s<>\\]+?\.(?:jpg|jpeg|png|webp)/gi) || [];
                    moreImgs.forEach(img => {
                        const clean = img.replace(/\\/g, '');
                        if (clean.includes('j/pi') || clean.includes('images')) {
                            images.add(clean.startsWith('http') ? clean : 'https:' + clean);
                        }
                    });
                } catch (e) {}
            }
        }

        return res.status(200).json({
            title,
            images: [...images],
            videos: [...videos],
        });

    } catch (e) {
        return res.status(500).json({ error: 'Erro ao processar: ' + e.message });
    }
};