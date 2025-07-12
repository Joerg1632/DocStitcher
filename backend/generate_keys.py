from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

# Генерация закрытого ключа
private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
)

# Сериализация и сохранение закрытого ключа
with open("private_key.pem", "wb") as f:
    f.write(private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    ))

# Получение открытого ключа
public_key = private_key.public_key()

# Сериализация и сохранение открытого ключа
with open("public_key.pem", "wb") as f:
    f.write(public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ))

print("[+] Ключи успешно сгенерированы: private_key.pem и public_key.pem")
