import base64

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

secret_key = "myencryptionkey"


# Function to encrypt the plain password
def encrypt_password(plain_password, key):
    # Ensure the key is 16, 24, or 32 bytes long for AES
    key = key.ljust(16)[:16].encode("utf-8")  # Adjust the key to be 16 bytes
    cipher = AES.new(key, AES.MODE_CBC)  # Using AES in CBC mode
    iv = cipher.iv  # Initialization vector
    encrypted_password = cipher.encrypt(
        pad(plain_password.encode("utf-8"), AES.block_size)
    )
    # Combine IV and encrypted password for storage
    return base64.b64encode(iv + encrypted_password).decode("utf-8")


# Function to decrypt the encrypted password
def decrypt_password(encrypted_password, key):
    key = key.ljust(16)[:16].encode("utf-8")  # Adjust the key to be 16 bytes
    encrypted_password = base64.b64decode(encrypted_password)
    iv = encrypted_password[:16]  # Extract the Initialization vector
    encrypted_data = encrypted_password[16:]  # The actual encrypted data
    cipher = AES.new(key, AES.MODE_CBC, iv=iv)
    return unpad(cipher.decrypt(encrypted_data), AES.block_size).decode("utf-8")
