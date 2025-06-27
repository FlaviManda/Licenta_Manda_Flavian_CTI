https://github.com/FlaviManda/Licenta_Manda_Flavian_CTI

Instalare și rulare
1. Clonează proiectul
git clone https://github.com/username/calorievisor.git
cd calorievisor

2. Creează și activează un mediu virtual
python -m venv venv
venv\\Scripts\\activate

3. Instalează dependențele
pip install -r requirements-food.txt

4. Configurează variabilele de mediu

Creează un fișier .env în directorul principal și adaugă cheile pentru Firebase, Nutritionix și Google APIs (vezi documentația proiectului pentru detalii).

5. Pornește serverul Flask
python app.py

6. Accesează aplicația
Deschide browserul la adresa:http://localhost:5000
