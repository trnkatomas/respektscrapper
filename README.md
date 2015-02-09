# respektscrapper

##Postup na instalaci

1. Ujistěte se, že jste v adresáři, kde máte uživatelská práva (např. ~/respekt)
2. stáhněte si oba dva soubory
3. `virtualenv venv`
4. `source venv/bin/activate`
5. `pip install -r requirements.txt`
6. `python scrapper.py`

Nápověda vše vysvětluje.

## Použití
Pro vytvoření ebooku je nutné spustit skript s přihlašovacím jménem a heslem. Defaultně se
vytvoří ebook v aktuálním adresáři. 

Ebook je možné poslat na zadaný mail.

## Příklady použití

Stáhne poslední číslo a pošle na mail
```
python scrapper -u prihlasovaci_jmeno -p prihlasovaci_heslo -e mail_kam_chci_poslat_ebook
```


Koukne se do hist.log a zjistí, jestli je k dispozici novější číslo než je uvedené v hist.log.

Formát čísla v hist.log je "cislo/rok" (např. `7/2015`)

```
python scrapper -u prihlasovaci_jmeno -p prihlasovaci_heslo -c hist.log
```


Stahne konkretni cislo s danou URL. Tu je možné získat z archivu a nebo spuštěním `python scrapper -l`

```
python scrapper -u jmeno -p heslo -s 'http://respekt.ihned.cz/?p=RA000A&archive[target_id]=4&archive[edition_number]=7&archive[year]=2015&archive[source_id]=10036250'
```
