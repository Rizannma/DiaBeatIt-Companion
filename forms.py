from flask_wtf import FlaskForm #This is for creating forms in Flask using WTForms
from wtforms import StringField, IntegerField, SelectField, PasswordField, BooleanField, FloatField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError, Optional, NumberRange
import re #This is for regex validation of names and passwords

class SignupForm(FlaskForm):
    # Base User Fields
    full_name = StringField('Full Name', validators=[DataRequired()])
    email = StringField('Email Address', validators=[DataRequired(), Email()])
    age = IntegerField('Age', validators=[DataRequired()])
    account_for = SelectField('Who is this account for?', choices=[
        ('', 'Select Type'),
        ('self', 'For myself'),
        ('other', 'For Someone Else (Child / Family Member)')
    ], validators=[DataRequired()])

    # "For Someone Else" Fields
    patient_name = StringField("Patient's Full Name", validators=[Optional()])
    patient_age = IntegerField("Patient's Age", validators=[Optional()])
    relationship = SelectField('Your Relationship to Patient', choices=[
        ('', 'Select Relationship'), ('Parent', 'Parent'), ('Guardian', 'Guardian'), ('Sibling', 'Sibling'), ('Spouse', 'Spouse')
    ], validators=[Optional()])
    consent = BooleanField('I have consent to manage this patient\'s data', validators=[Optional()])

    # Password Fields
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])

    # Custom Validators
    def validate_full_name(self, field):
        if not re.match(r'^[A-Za-z]+,\s+[A-Za-z]+(?:\s+[A-Za-z]+)*$', field.data.strip()):
            raise ValidationError("Enter name as Surname, First Name (middle name optional).")

    def validate_patient_name(self, field):
        if field.data and not re.match(r'^[A-Za-z]+,\s+[A-Za-z]+(?:\s+[A-Za-z]+)*$', field.data.strip()):
            raise ValidationError("Enter patient name as Surname, First Name (middle name optional).")

    def validate_age(self, field):
        if field.data < 18:
            raise ValidationError("You must be 18 years or older to create an account.")

    def validate_password(self, field):
        p = field.data
        if not (any(c.isupper() for c in p) and any(c.islower() for c in p) and 
                any(c.isdigit() for c in p) and any(not c.isalnum() for c in p)):
            raise ValidationError("Password must include upper, lower, number, and special character.")


class LoginForm(FlaskForm):
    email = StringField('Email Address', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])


class ConfirmForm(FlaskForm):
    otp = StringField('OTP Code', validators=[DataRequired(), Length(min=6, max=6)])


class ResetPasswordForm(FlaskForm):
    password = PasswordField('New Password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField('Confirm New Password', validators=[DataRequired(), EqualTo('password')])

    def validate_password(self, field):
        p = field.data
        if not (any(c.isupper() for c in p) and any(c.islower() for c in p) and 
                any(c.isdigit() for c in p) and any(not c.isalnum() for c in p)):
            raise ValidationError("Password must include upper, lower, number, and special character.")


class ProfileForm(FlaskForm):
    gender = SelectField('Gender', choices=[
        ('', 'Select Gender'),
        ('Male', 'Male'),
        ('Female', 'Female'),
        ('Non-binary', 'Non-binary'),
        ('Prefer not to say', 'Prefer not to say')
    ], validators=[Optional()])

    family_history_diabetes = SelectField('Family History of Diabetes', choices=[
        ('', 'Select an option'),
        ('Yes', 'Yes'),
        ('No', 'No')
    ], validators=[Optional()])

    cardiovascular_history = SelectField('Cardiovascular History', choices=[
        ('', 'Select an option'),
        ('Yes', 'Yes'),
        ('No', 'No')
    ], validators=[Optional()])

    hypertension_history = SelectField('Hypertension History', choices=[
        ('', 'Select an option'),
        ('Yes', 'Yes'),
        ('No', 'No')
    ], validators=[Optional()])

    height_cm = FloatField('Height (cm)', validators=[
        Optional(),
        NumberRange(min=50, max=250, message='Height must be between 50 and 250 cm')
    ])

    weight_kg = FloatField('Weight (kg)', validators=[
        Optional(),
        NumberRange(min=20, max=300, message='Weight must be between 20 and 300 kg')
    ])

    hip_circumference = FloatField('Hip Circumference (cm)', validators=[
        Optional(),
        NumberRange(min=50, max=150, message='Hip circumference must be between 50 and 150 cm')
    ])

    hba1c = FloatField('HbA1c (%)', validators=[
        Optional(),
        NumberRange(min=4, max=15, message='HbA1c must be between 4 and 15 percent')
    ])

    cholesterol_total = FloatField('Total Cholesterol (mg/dL)', validators=[
        Optional(),
        NumberRange(min=100, max=400, message='Total cholesterol must be between 100 and 400 mg/dL')
    ])

    triglyceride = FloatField('Triglyceride (mg/dL)', validators=[
        Optional(),
        NumberRange(min=50, max=500, message='Triglyceride must be between 50 and 500 mg/dL')
    ])
