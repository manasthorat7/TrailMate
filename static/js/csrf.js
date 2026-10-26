/**
 * Attach the Flask-WTF CSRF token to same-origin mutating fetch() requests.
 *
 * The token is rendered once in base.html as <meta name="csrf-token">. This
 * keeps JSON/fetch POSTs compatible with CSRFProtect without weakening the
 * protection or requiring callers to make a separate token request.
 */
(function () {
    'use strict';

    const meta = document.querySelector('meta[name="csrf-token"]');
    if (!meta || typeof window.fetch !== 'function') {
        return;
    }

    const token = meta.getAttribute('content');
    if (!token) {
        return;
    }

    const originalFetch = window.fetch.bind(window);
    const safeMethods = ['GET', 'HEAD', 'OPTIONS', 'TRACE'];

    window.fetch = function (input, init) {
        const request = (typeof Request !== 'undefined' && input instanceof Request) ? input : null;
        const method = String(
            (init && init.method) || (request && request.method) || 'GET'
        ).toUpperCase();

        let url;
        try {
            url = new URL(request ? request.url : input, window.location.href);
        } catch (error) {
            return originalFetch(input, init);
        }

        if (safeMethods.includes(method) || url.origin !== window.location.origin) {
            return originalFetch(input, init);
        }

        const headers = new Headers(
            (init && init.headers) || (request && request.headers) || {}
        );
        if (!headers.has('X-CSRFToken')) {
            headers.set('X-CSRFToken', token);
        }

        return originalFetch(input, Object.assign({}, init, { headers }));
    };
})();
