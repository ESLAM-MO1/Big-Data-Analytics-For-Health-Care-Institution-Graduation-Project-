FROM python:3.11

RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

WORKDIR /app

COPY --chown=user app/backend/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user app/backend/ /app

EXPOSE 7860

CMD ["python", "manage.py", "runserver", "0.0.0.0:7860"]