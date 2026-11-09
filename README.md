<img width="1400" height="450" alt="image" src="https://github.com/user-attachments/assets/9c740d91-757a-4fb5-89b3-c3def14ae6e6" />

# 📘 Guía de Git con ramas – Proyecto Óptica Amaru

## 1. Conceptos básicos de Git

| Palabra | Significado |
|:---|:---|
| **Repositorio (repo)** | La carpeta del proyecto guardada en GitHub. |
| **Clone** | Descargar el repositorio al computador por primera vez. Nunca se descarga como ZIP. |
| **Rama (branch)** | Una copia paralela del proyecto para trabajar sin afectar a los demás. |
| **main** | La rama oficial. Siempre debe funcionar y nadie trabaja directamente en ella. |
| **Commit** | Guardar una "foto" de los cambios en el computador, con un mensaje. |
| **Push** | Subir los commits de tu rama a GitHub. No modifica `main`. |
| **Pull** | Bajar desde GitHub los cambios que subieron los demás. |
| **Pull Request (PR)** | Solicitud en GitHub para juntar tu rama con `main`. |
| **Merge** | Juntar dos ramas en una. |
| **Conflicto** | Ocurre cuando dos personas modifican las mismas líneas y Git no sabe cuál versión dejar. |

---

## 2. Instalación de Pillow para imágenes en Python

Si necesitas trabajar con imágenes desde Python, instala Pillow:

```powershell
pip install Pillow
```

> **Nota:** Pillow permite procesar imágenes desde Python. No es necesario instalarlo para mostrar imágenes en el README.

### Agregar imágenes al README

1. Crear una carpeta llamada `imagenes` en la raíz del proyecto.
2. Guardar las imágenes dentro de esa carpeta.
3. Abrir el archivo `README.md`.
4. Insertar la imagen utilizando Markdown:

```markdown
![Logo del proyecto](imagenes/logo.png)
```

Para modificar el tamaño de una imagen:

```html
<img src="imagenes/logo.png" width="300">
```

**Ejemplo de organización:**

```text
OpticaAmaru/
├── README.md
├── imagenes/
│   ├── logo.png
│   ├── inicio.png
│   └── login.png
├── OpticaAmaru/
└── opticaApp/
```

---

## 3. Guía para trabajar con Git y ramas

### Paso 1. Antes de empezar, trae los cambios nuevos

Abre PowerShell en la carpeta del proyecto y ejecuta:

```powershell
git status
git pull
```

`git status` debe aparecer limpio o mostrar solamente archivos `__pycache__`.

Si aparecen carpetas `__pycache__` que no necesitas conservar, puedes descartarlas con:

```powershell
git restore OpticaAmaru/__pycache__ opticaApp/__pycache__ opticaApp/migrations/__pycache__
```

Si tienes cambios tuyos sin guardar, realiza primero el paso 3.

### Paso 2. Trabaja en tu propia rama

Este comando se utiliza solamente la primera vez que creas tu rama:

```powershell
git checkout -b interfaces-fran
```

Así puedes trabajar sin modificar directamente `main`.

### Paso 3. Guarda tus cambios en un commit

Primero revisa qué archivos modificaste:

```powershell
git status
```

Agrega únicamente los archivos que modificaste:

```powershell
git add opticaApp/apps.py templates/base.html OpticaAmaru/urls.py
```

Guarda los cambios:

```powershell
git commit -m "Descripción corta de lo que hiciste"
```

**Importante:**
- Nombra los archivos uno por uno.
- No uses `git add .` ni `git commit -a`, porque podrían incluir archivos innecesarios.
- Evita subir archivos `__pycache__`.
- Revisa que no aparezcan `ca.pem`, `.env` ni archivos con contraseñas.
- Nunca subas credenciales al repositorio público.

### Paso 4. Actualiza tu rama con los cambios de tus compañeros

Antes de subir tu trabajo, trae los cambios que se hayan agregado a `main`:

```powershell
git pull origin main
```

Si se abre Vim, escribe:

```text
:wq
```

Después presiona Enter para guardar y salir.

### Paso 5. Comprueba que el proyecto funcione

Ejecuta las migraciones:

```powershell
python manage.py migrate
```

Inicia el servidor:

```powershell
python manage.py runserver
```

Comprueba que las páginas y funcionalidades que modificaste funcionen correctamente.

### Paso 6. Sube tu rama a GitHub

Ejecuta:

```powershell
git push -u origin interfaces-fran
```

La primera vez debes utilizar ese comando.

En las siguientes ocasiones basta con:

```powershell
git push
```

### Paso 7. Solicita que integren tus cambios a main

1. Entra al repositorio en GitHub.
2. Aparecerá la opción **Compare & pull request**.
3. Presiona el botón.
4. Escribe una descripción corta de los cambios realizados.
5. Envía el Pull Request.
6. Avisa al equipo para que revise tu trabajo.

Una vez revisado y aprobado, se podrá integrar mediante Merge a `main`.

---

## 4. Problemas frecuentes y soluciones

| Problema | Solución |
|:---|:---|
| `Permission denied` o error `403` | Tu cuenta no tiene permisos. Yoko debe agregarte en Settings → Collaborators. |
| `rejected ... fetch first` o `non-fast-forward` | Alguien subió cambios antes que tú. Ejecuta `git pull origin main` y luego vuelve a intentar el push. |
| `CONFLICT` al hacer pull | Abre el archivo en VS Code, revisa qué versión conservar y resuelve el conflicto. Puedes utilizar Accept Both Changes si corresponde. Después ejecuta `git add <archivo>` y `git commit`. |
| Te equivocaste en el último commit | Puedes utilizar `git reset --soft HEAD~1` para deshacer el último commit sin perder los cambios. |

---

## 5. Reglas del equipo para evitar conflictos

1. Hacer un `git pull` al comenzar a trabajar.
2. Hacer otro `git pull origin main` antes de subir los cambios.
3. Avisar antes de modificar archivos importantes como:
   - `models.py`
   - `urls.py`
   - `settings.py`
   - `base.html`
4. Las migraciones las crea una sola persona para evitar conflictos.
5. Cada integrante trabaja en su propia rama.
6. Nadie modifica directamente la rama `main`.
7. Revisar los archivos antes de subirlos para evitar publicar contraseñas o credenciales.

---

## 6. Comandos que conviene recordar

| Comando | Función |
|:---|:---|
| `git status` | Revisar el estado de los archivos. |
| `git pull` | Descargar cambios del repositorio remoto. |
| `git checkout -b nombre-rama` | Crear una rama nueva y cambiarse a ella. |
| `git checkout nombre-rama` | Cambiar de rama. |
| `git add archivo` | Preparar un archivo para el commit. |
| `git commit -m "mensaje"` | Guardar los cambios localmente. |
| `git pull origin main` | Traer los cambios de main. |
| `git push` | Subir los commits de tu rama. |
| `git branch` | Ver las ramas existentes. |

---

**💡 Recomendación:** Si algún paso muestra un mensaje de error que no entiendes, copia el mensaje completo y compártelo con el equipo antes de ejecutar otros comandos. Así evitamos perder cambios o generar conflictos innecesarios.
