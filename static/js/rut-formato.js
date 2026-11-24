/**
 * Formato automático y validación en tiempo real de RUT chileno - Óptica Amaru
 * Se aplica automáticamente a los campos de RUT en formularios públicos.
 */
(function () {
    'use strict';

    function limpiarRut(valor) {
        var limpio = (valor || '').toUpperCase().replace(/[^0-9K]/g, '');
        // La 'K' solo puede ir como dígito verificador al final
        if (limpio.length > 1) {
            var cuerpo = limpio.slice(0, -1).replace(/K/g, '');
            var dv = limpio.slice(-1);
            limpio = cuerpo + dv;
        }
        return limpio.slice(0, 9);
    }

    function formatearRut(limpio) {
        if (!limpio) return '';
        if (limpio.length === 1) return limpio;

        var cuerpo = limpio.slice(0, -1);
        var dv = limpio.slice(-1);
        var cuerpoFormateado = cuerpo.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
        return cuerpoFormateado + '-' + dv;
    }

    function calcularDv(cuerpo) {
        var suma = 0;
        var multiplicador = 2;
        for (var i = cuerpo.length - 1; i >= 0; i--) {
            suma += parseInt(cuerpo.charAt(i), 10) * multiplicador;
            multiplicador = multiplicador === 7 ? 2 : multiplicador + 1;
        }
        var resto = 11 - (suma % 11);
        if (resto === 11) return '0';
        if (resto === 10) return 'K';
        return String(resto);
    }

    function validarRutLimpio(limpio) {
        if (limpio.length < 8 || limpio.length > 9) {
            return { completo: false, valido: false };
        }
        var cuerpo = limpio.slice(0, -1);
        var dv = limpio.slice(-1);
        if (!/^\d+$/.test(cuerpo)) {
            return { completo: true, valido: false };
        }
        return {
            completo: true,
            valido: dv === calcularDv(cuerpo)
        };
    }

    function obtenerFeedbackEl(input) {
        var parent = input.parentElement;
        if (!parent) return null;
        var existing = parent.querySelector('.rut-feedback[data-for="' + input.id + '"]');
        if (existing) return existing;

        var feedback = document.createElement('div');
        feedback.className = 'rut-feedback';
        feedback.setAttribute('data-for', input.id || input.name || 'rut');
        feedback.setAttribute('aria-live', 'polite');
        input.insertAdjacentElement('afterend', feedback);
        return feedback;
    }

    function actualizarEstadoVisual(input, feedback, esBlur) {
        var limpio = limpiarRut(input.value);

        if (!limpio) {
            input.classList.remove('is-valid', 'is-invalid');
            if (feedback) {
                feedback.textContent = '';
                feedback.className = 'rut-feedback';
            }
            return true;
        }

        var resultado = validarRutLimpio(limpio);

        if (!resultado.completo) {
            input.classList.remove('is-valid');
            if (esBlur) {
                input.classList.add('is-invalid');
                if (feedback) {
                    feedback.textContent = 'RUT incompleto. Ej: 12.345.678-9';
                    feedback.className = 'rut-feedback is-error';
                }
                return false;
            }
            input.classList.remove('is-invalid');
            if (feedback) {
                feedback.textContent = '';
                feedback.className = 'rut-feedback';
            }
            return false;
        }

        if (resultado.valido) {
            input.classList.remove('is-invalid');
            input.classList.add('is-valid');
            if (feedback) {
                feedback.textContent = '✓ RUT válido';
                feedback.className = 'rut-feedback is-ok';
            }
            return true;
        } else {
            input.classList.remove('is-valid');
            input.classList.add('is-invalid');
            if (feedback) {
                feedback.textContent = 'Dígito verificador inválido. Revisa tu RUT.';
                feedback.className = 'rut-feedback is-error';
            }
            return false;
        }
    }

    function contarCaracteresValidosAntes(texto, pos) {
        return limpiarRut(texto.slice(0, pos)).length;
    }

    function posicionParaCantidadValida(textoFormateado, cantidad) {
        if (cantidad <= 0) return 0;
        var vistos = 0;
        for (var i = 0; i < textoFormateado.length; i++) {
            if (/[0-9K]/i.test(textoFormateado.charAt(i))) {
                vistos++;
                if (vistos === cantidad) {
                    return i + 1;
                }
            }
        }
        return textoFormateado.length;
    }

    function inicializarCampoRut(input) {
        if (input.dataset.rutInit === '1') return;
        input.dataset.rutInit = '1';

        if (!input.getAttribute('maxlength')) {
            input.setAttribute('maxlength', '12');
        }
        input.setAttribute('autocomplete', 'off');
        input.setAttribute('autocapitalize', 'characters');

        var feedback = obtenerFeedbackEl(input);

        // Si el input ya viene con valor (por ejemplo, tras un error de validación del servidor)
        if (input.value) {
            var limpioInicial = limpiarRut(input.value);
            input.value = formatearRut(limpioInicial);
            actualizarEstadoVisual(input, feedback, false);
        }

        input.addEventListener('input', function () {
            var cursor = input.selectionStart || 0;
            var antesValidos = contarCaracteresValidosAntes(input.value, cursor);
            var limpio = limpiarRut(input.value);
            var formateado = formatearRut(limpio);

            if (input.value !== formateado) {
                input.value = formateado;
                var nuevaPos = posicionParaCantidadValida(formateado, antesValidos);
                if (typeof input.setSelectionRange === 'function') {
                    input.setSelectionRange(nuevaPos, nuevaPos);
                }
            }

            actualizarEstadoVisual(input, feedback, false);
        });

        input.addEventListener('blur', function () {
            if (input.value) {
                input.value = formatearRut(limpiarRut(input.value));
            }
            actualizarEstadoVisual(input, feedback, true);
        });

        var form = input.form;
        if (form && form.dataset.rutSubmitInit !== '1') {
            form.dataset.rutSubmitInit = '1';
            form.addEventListener('submit', function (event) {
                var campos = form.querySelectorAll('input[name="rut"], input[data-rut-input="true"]');
                for (var i = 0; i < campos.length; i++) {
                    var campo = campos[i];
                    if (!campo.value.trim()) continue;
                    var fb = obtenerFeedbackEl(campo);
                    var ok = actualizarEstadoVisual(campo, fb, true);
                    if (!ok) {
                        event.preventDefault();
                        campo.focus();
                        break;
                    }
                }
            });
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        var campos = document.querySelectorAll('input[name="rut"], input[data-rut-input="true"]');
        campos.forEach(inicializarCampoRut);
    });
})();
