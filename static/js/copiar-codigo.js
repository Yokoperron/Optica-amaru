/**
 * Copiado interactivo global de códigos y folios - Óptica Amaru
 * Uso: añadir data-copy-code="CODIGO" (y clase .codigo-copiable) a cualquier elemento.
 */
(function () {
    'use strict';

    var MSG_HOVER = 'Haz clic para copiar';
    var MSG_COPIED = '¡Código copiado!';
    var MSG_ERROR = 'No se pudo copiar. Mantén presionado el código para copiarlo.';
    var RESET_DELAY_MS = 2200;

    var tooltipEl = null;
    var liveRegionEl = null;
    var activeTarget = null;
    var hideTimer = null;
    var isCopiedState = false;

    function ensureTooltip() {
        if (tooltipEl) return tooltipEl;
        tooltipEl = document.createElement('div');
        tooltipEl.className = 'copia-tooltip';
        tooltipEl.setAttribute('aria-hidden', 'true');
        document.body.appendChild(tooltipEl);
        return tooltipEl;
    }

    function ensureLiveRegion() {
        if (liveRegionEl) return liveRegionEl;
        liveRegionEl = document.createElement('div');
        liveRegionEl.className = 'copia-sr-only';
        liveRegionEl.setAttribute('role', 'status');
        liveRegionEl.setAttribute('aria-live', 'polite');
        liveRegionEl.setAttribute('aria-atomic', 'true');
        document.body.appendChild(liveRegionEl);
        return liveRegionEl;
    }

    function announce(message) {
        var region = ensureLiveRegion();
        region.textContent = '';
        window.setTimeout(function () {
            region.textContent = message;
        }, 20);
    }

    function positionTooltip(target) {
        if (!tooltipEl || !target) return;
        var rect = target.getBoundingClientRect();
        var tipRect = tooltipEl.getBoundingClientRect();
        var margin = 8;

        var top = rect.top - tipRect.height - margin;
        var placement = 'top';
        if (top < 8) {
            top = rect.bottom + margin;
            placement = 'bottom';
        }

        var left = rect.left + (rect.width / 2) - (tipRect.width / 2);
        var maxLeft = window.innerWidth - tipRect.width - 10;
        if (left < 10) left = 10;
        if (left > maxLeft) left = Math.max(10, maxLeft);

        tooltipEl.style.top = Math.round(top) + 'px';
        tooltipEl.style.left = Math.round(left) + 'px';
        tooltipEl.setAttribute('data-placement', placement);
    }

    function showTooltip(target, message, state) {
        var tip = ensureTooltip();
        tip.classList.remove('is-copied', 'is-error', 'is-visible');

        if (state === 'copied') {
            tip.innerHTML = '<span class="copia-tooltip-icon" aria-hidden="true">✓</span><span>' + message + '</span>';
            tip.classList.add('is-copied');
        } else if (state === 'error') {
            tip.innerHTML = '<span>' + message + '</span>';
            tip.classList.add('is-error');
        } else {
            tip.textContent = message;
        }

        tip.classList.add('is-visible');
        activeTarget = target;
        positionTooltip(target);
    }

    function hideTooltip() {
        if (!tooltipEl) return;
        tooltipEl.classList.remove('is-visible', 'is-copied', 'is-error');
        isCopiedState = false;
        activeTarget = null;
    }

    function fallbackCopy(text) {
        var textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.setAttribute('readonly', '');
        textarea.style.position = 'fixed';
        textarea.style.top = '-9999px';
        textarea.style.left = '-9999px';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);

        var selection = document.getSelection();
        var selectedRange = selection && selection.rangeCount > 0 ? selection.getRangeAt(0) : null;

        textarea.select();
        textarea.setSelectionRange(0, text.length);

        var ok = false;
        try {
            ok = document.execCommand('copy');
        } catch (err) {
            ok = false;
        }

        document.body.removeChild(textarea);
        if (selectedRange && selection) {
            selection.removeAllRanges();
            selection.addRange(selectedRange);
        }
        return ok;
    }

    function copyText(text) {
        if (navigator.clipboard && window.isSecureContext) {
            return navigator.clipboard.writeText(text).catch(function () {
                if (fallbackCopy(text)) {
                    return Promise.resolve();
                }
                return Promise.reject(new Error('Clipboard unavailable'));
            });
        }

        return new Promise(function (resolve, reject) {
            if (fallbackCopy(text)) {
                resolve();
            } else {
                reject(new Error('Fallback copy failed'));
            }
        });
    }

    function handleCopy(target) {
        var code = (target.getAttribute('data-copy-code') || target.textContent || '').trim();
        if (!code) return;

        window.clearTimeout(hideTimer);

        copyText(code).then(function () {
            isCopiedState = true;
            target.classList.add('is-copied');
            showTooltip(target, MSG_COPIED, 'copied');
            announce('Código ' + code + ' copiado al portapapeles.');

            hideTimer = window.setTimeout(function () {
                target.classList.remove('is-copied');
                hideTooltip();
            }, RESET_DELAY_MS);
        }).catch(function () {
            isCopiedState = true;
            showTooltip(target, MSG_ERROR, 'error');
            announce(MSG_ERROR);

            hideTimer = window.setTimeout(function () {
                hideTooltip();
            }, RESET_DELAY_MS + 1000);
        });
    }

    function initCopyElements() {
        var elements = document.querySelectorAll('[data-copy-code]');
        elements.forEach(function (el) {
            el.classList.add('codigo-copiable');
            if (!el.hasAttribute('tabindex') && el.tagName !== 'BUTTON' && el.tagName !== 'A') {
                el.setAttribute('tabindex', '0');
            }
            if (!el.hasAttribute('role') && el.tagName !== 'BUTTON' && el.tagName !== 'A') {
                el.setAttribute('role', 'button');
            }
            if (!el.hasAttribute('aria-label')) {
                var code = (el.getAttribute('data-copy-code') || el.textContent || '').trim();
                if (code) {
                    el.setAttribute('aria-label', 'Copiar código ' + code);
                }
            }
            if (el.hasAttribute('title')) {
                el.removeAttribute('title');
            }
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        initCopyElements();

        document.addEventListener('click', function (event) {
            var target = event.target.closest('[data-copy-code]');
            if (!target) {
                if (isCopiedState) {
                    window.clearTimeout(hideTimer);
                    if (activeTarget) activeTarget.classList.remove('is-copied');
                    hideTooltip();
                }
                return;
            }
            handleCopy(target);
        });

        document.addEventListener('keydown', function (event) {
            var target = event.target.closest('[data-copy-code]');
            if (!target) return;
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                handleCopy(target);
            } else if (event.key === 'Escape' && activeTarget) {
                window.clearTimeout(hideTimer);
                activeTarget.classList.remove('is-copied');
                hideTooltip();
            }
        });

        document.addEventListener('pointerenter', function (event) {
            if (event.pointerType === 'touch') return;
            var target = event.target.closest('[data-copy-code]');
            if (!target) return;
            if (isCopiedState && activeTarget === target) return;
            window.clearTimeout(hideTimer);
            isCopiedState = false;
            showTooltip(target, MSG_HOVER, 'hover');
        }, true);

        document.addEventListener('pointerleave', function (event) {
            if (event.pointerType === 'touch') return;
            var target = event.target.closest('[data-copy-code]');
            if (!target) return;
            if (isCopiedState) return;
            if (activeTarget === target) {
                hideTooltip();
            }
        }, true);

        document.addEventListener('focusin', function (event) {
            var target = event.target.closest('[data-copy-code]');
            if (!target) return;
            if (isCopiedState && activeTarget === target) return;
            if (target.matches(':focus-visible')) {
                showTooltip(target, MSG_HOVER, 'hover');
            }
        });

        document.addEventListener('focusout', function (event) {
            var target = event.target.closest('[data-copy-code]');
            if (!target) return;
            if (!isCopiedState && activeTarget === target) {
                hideTooltip();
            }
        });

        window.addEventListener('scroll', function () {
            if (activeTarget && tooltipEl && tooltipEl.classList.contains('is-visible')) {
                positionTooltip(activeTarget);
            }
        }, { passive: true });

        window.addEventListener('resize', function () {
            if (activeTarget && tooltipEl && tooltipEl.classList.contains('is-visible')) {
                positionTooltip(activeTarget);
            }
        }, { passive: true });
    });
})();
